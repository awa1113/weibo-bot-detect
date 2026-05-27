# 微博方向社交机器人检测V1.0

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import torch
from sklearn.metrics import accuracy_score, precision_recall_fscore_support
from torch import nn
from torch.optim import AdamW
from torch.utils.data import DataLoader, Dataset


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

from app.models.fusion_model import TextFusionClassifier  # noqa: E402


@dataclass
class TrainArtifacts:
    des_tensor: torch.Tensor
    tweet_tensor: torch.Tensor
    labels: torch.Tensor
    train_idx: torch.Tensor
    val_idx: torch.Tensor
    test_idx: torch.Tensor


class IndexedEmbeddingDataset(Dataset):
    def __init__(
        self,
        des_tensor: torch.Tensor,
        tweet_tensor: torch.Tensor,
        labels: torch.Tensor,
        indices: torch.Tensor,
    ) -> None:
        self.des_tensor = des_tensor
        self.tweet_tensor = tweet_tensor
        self.labels = labels
        self.indices = indices.long()

    def __len__(self) -> int:
        return int(self.indices.shape[0])

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        row = int(self.indices[index].item())
        return self.des_tensor[row], self.tweet_tensor[row], self.labels[row]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train text fusion classifier.")
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--epochs", type=int, default=6)
    parser.add_argument("--batch-size", type=int, default=2048)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--num-workers", type=int, default=0)
    parser.add_argument("--mixed-precision", action="store_true")
    parser.add_argument("--multi-gpu", action="store_true")
    return parser.parse_args()


def load_artifacts(input_dir: Path) -> TrainArtifacts:
    return TrainArtifacts(
        des_tensor=torch.load(input_dir / "des_tensor.pt", map_location="cpu").float(),
        tweet_tensor=torch.load(input_dir / "tweets_tensor.pt", map_location="cpu").float(),
        labels=torch.load(input_dir / "label.pt", map_location="cpu").long(),
        train_idx=torch.load(input_dir / "train_idx.pt", map_location="cpu").long(),
        val_idx=torch.load(input_dir / "val_idx.pt", map_location="cpu").long(),
        test_idx=torch.load(input_dir / "test_idx.pt", map_location="cpu").long(),
    )


def create_dataloader(dataset: Dataset, batch_size: int, shuffle: bool, num_workers: int) -> DataLoader:
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        num_workers=num_workers,
        pin_memory=torch.cuda.is_available(),
        persistent_workers=num_workers > 0,
    )


def evaluate(model: nn.Module, loader: DataLoader, device: torch.device) -> dict[str, float]:
    model.eval()
    predictions: list[int] = []
    labels: list[int] = []
    with torch.inference_mode():
        for des, tweet, target in loader:
            des = des.to(device, non_blocking=True)
            tweet = tweet.to(device, non_blocking=True)
            logits = model(des, tweet)
            predictions.extend(torch.argmax(logits, dim=1).cpu().tolist())
            labels.extend(target.tolist())
    accuracy = accuracy_score(labels, predictions)
    precision, recall, f1, _ = precision_recall_fscore_support(labels, predictions, average="binary", zero_division=0)
    return {
        "accuracy": round(float(accuracy), 4),
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "f1": round(float(f1), 4),
    }


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = load_artifacts(args.input_dir)

    train_loader = create_dataloader(
        IndexedEmbeddingDataset(artifacts.des_tensor, artifacts.tweet_tensor, artifacts.labels, artifacts.train_idx),
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.num_workers,
    )
    val_loader = create_dataloader(
        IndexedEmbeddingDataset(artifacts.des_tensor, artifacts.tweet_tensor, artifacts.labels, artifacts.val_idx),
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.num_workers,
    )
    test_loader = create_dataloader(
        IndexedEmbeddingDataset(artifacts.des_tensor, artifacts.tweet_tensor, artifacts.labels, artifacts.test_idx),
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.num_workers,
    )

    torch.set_float32_matmul_precision("high")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model: nn.Module = TextFusionClassifier().to(device)
    if args.multi_gpu and torch.cuda.device_count() >= 2:
        model = nn.DataParallel(model)

    criterion = nn.CrossEntropyLoss()
    optimizer = AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    scaler = torch.amp.GradScaler("cuda", enabled=args.mixed_precision and torch.cuda.is_available())

    history: list[dict[str, float | int]] = []
    best_f1 = -1.0

    for epoch in range(1, args.epochs + 1):
        model.train()
        running_loss = 0.0
        for des, tweet, target in train_loader:
            des = des.to(device, non_blocking=True)
            tweet = tweet.to(device, non_blocking=True)
            target = target.to(device, non_blocking=True)
            optimizer.zero_grad(set_to_none=True)
            with torch.amp.autocast("cuda", enabled=args.mixed_precision and torch.cuda.is_available()):
                logits = model(des, tweet)
                loss = criterion(logits, target)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            running_loss += float(loss.item())

        val_metrics = evaluate(model, val_loader, device)
        epoch_summary = {
            "epoch": epoch,
            "train_loss": round(running_loss / max(len(train_loader), 1), 4),
            **val_metrics,
        }
        history.append(epoch_summary)
        print(json.dumps(epoch_summary, ensure_ascii=False))
        if val_metrics["f1"] > best_f1:
            best_f1 = val_metrics["f1"]
            state_dict = model.module.state_dict() if isinstance(model, nn.DataParallel) else model.state_dict()
            torch.save(state_dict, args.output_dir / "text_fusion_classifier.pt")

    best_state = torch.load(args.output_dir / "text_fusion_classifier.pt", map_location=device)
    if isinstance(model, nn.DataParallel):
        model.module.load_state_dict(best_state)
    else:
        model.load_state_dict(best_state)
    test_metrics = evaluate(model, test_loader, device)
    metadata = {
        "updated_at": datetime.now().isoformat(),
        "metrics": {
            "best_val_f1": best_f1,
            "test_accuracy": test_metrics["accuracy"],
            "test_precision": test_metrics["precision"],
            "test_recall": test_metrics["recall"],
            "test_f1": test_metrics["f1"],
        },
        "history": history,
        "notes": "Generated by train_text_fusion.py with dual-GPU DataParallel training.",
    }
    (args.output_dir / "model_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"stage": "test", **test_metrics}, ensure_ascii=False))


if __name__ == "__main__":
    main()
