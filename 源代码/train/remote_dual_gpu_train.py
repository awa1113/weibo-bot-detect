# 微博方向社交机器人检测V1.0

from __future__ import annotations

import argparse
from pathlib import Path
import posixpath
import stat
import time

try:
    import paramiko
except ImportError as error:  # pragma: no cover
    raise SystemExit("Please install paramiko: python -m pip install paramiko") from error


MANAGED_SERVICES = ("qwen-vllm.service", "cosyvoice-tts.service")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Remote dual-GPU training orchestrator.")
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--local-project-root", type=Path, required=True)
    parser.add_argument("--local-data-dir", type=Path, required=True)
    parser.add_argument("--local-output-dir", type=Path, required=True)
    parser.add_argument("--remote-workdir", default="/root/social-bot-detector-run")
    parser.add_argument("--epochs", type=int, default=6)
    parser.add_argument("--batch-size", type=int, default=2048)
    return parser.parse_args()


def connect(args: argparse.Namespace) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=args.host,
        port=args.port,
        username=args.username,
        password=args.password,
        timeout=30,
    )
    return client


def run(client: paramiko.SSHClient, command: str) -> tuple[int, str, str]:
    stdin, stdout, stderr = client.exec_command(command)
    exit_status = stdout.channel.recv_exit_status()
    return exit_status, stdout.read().decode("utf-8", errors="ignore"), stderr.read().decode("utf-8", errors="ignore")


def is_service_active(client: paramiko.SSHClient, service_name: str) -> bool:
    exit_code, stdout, _ = run(client, f"systemctl is-active {service_name} || true")
    return exit_code == 0 and stdout.strip() == "active"


def append_log(logs: list[str], command: str, exit_code: int, stdout: str, stderr: str) -> None:
    logs.append(f"$ {command}\n[exit={exit_code}]\n{stdout}\n{stderr}\n")


def wait_for_gpu_release(client: paramiko.SSHClient, timeout_seconds: int = 180, threshold_mib: int = 1024) -> None:
    deadline = time.time() + timeout_seconds
    query = "nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits"
    last_values: list[int] = []
    while time.time() < deadline:
        exit_code, stdout, _ = run(client, query)
        if exit_code == 0:
            values = [int(item.strip()) for item in stdout.splitlines() if item.strip()]
            last_values = values
            if values and all(value <= threshold_mib for value in values):
                return
        time.sleep(5)
    raise SystemExit(f"GPU memory was not released after stopping inference services. Current usage: {last_values}")


def ensure_remote_dir(sftp: paramiko.SFTPClient, remote_path: str) -> None:
    segments = remote_path.strip("/").split("/")
    current = ""
    for segment in segments:
        current = f"{current}/{segment}" if current else f"/{segment}"
        try:
            sftp.stat(current)
        except OSError:
            sftp.mkdir(current)


def upload_file(sftp: paramiko.SFTPClient, local_path: Path, remote_path: str) -> None:
    ensure_remote_dir(sftp, posixpath.dirname(remote_path))
    sftp.put(str(local_path), remote_path)


def upload_tree(sftp: paramiko.SFTPClient, local_root: Path, remote_root: str) -> None:
    for path in local_root.rglob("*"):
        remote_path = posixpath.join(remote_root, path.relative_to(local_root).as_posix())
        if path.is_dir():
            ensure_remote_dir(sftp, remote_path)
        else:
            upload_file(sftp, path, remote_path)


def download_tree(sftp: paramiko.SFTPClient, remote_root: str, local_root: Path) -> None:
    local_root.mkdir(parents=True, exist_ok=True)
    for entry in sftp.listdir_attr(remote_root):
        remote_path = posixpath.join(remote_root, entry.filename)
        local_path = local_root / entry.filename
        if stat.S_ISDIR(entry.st_mode):
            download_tree(sftp, remote_path, local_path)
        else:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            sftp.get(remote_path, str(local_path))


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def main() -> None:
    args = parse_args()
    client = connect(args)
    sftp = client.open_sftp()

    remote_train_root = args.remote_workdir
    remote_source_root = posixpath.join(remote_train_root, "source")
    remote_data_root = posixpath.join(remote_train_root, "data")
    remote_output_root = posixpath.join(remote_train_root, "output")

    args.local_output_dir.mkdir(parents=True, exist_ok=True)
    stop_logs: list[str] = []
    stdout = ""
    stderr = ""
    service_states: dict[str, bool] = {}
    try:
        service_states = {service_name: is_service_active(client, service_name) for service_name in MANAGED_SERVICES}
        stop_logs.append(
            "Service states before training:\n"
            + "\n".join(f"{service_name}: {'active' if is_active else 'inactive'}" for service_name, is_active in service_states.items())
            + "\n"
        )

        stop_commands: list[str] = []
        if service_states["qwen-vllm.service"]:
            stop_commands.extend(
                [
                    "systemctl stop qwen-vllm.service || true",
                    "docker stop vllm-server-internal || true",
                    "docker rm -f vllm-server-internal || true",
                ]
            )
        if service_states["cosyvoice-tts.service"]:
            stop_commands.append("systemctl stop cosyvoice-tts.service || true")

        for command in stop_commands:
            exit_code, out, err = run(client, command)
            append_log(stop_logs, command, exit_code, out, err)

        wait_for_gpu_release(client)
        exit_code, out, err = run(client, "nvidia-smi")
        append_log(stop_logs, "nvidia-smi", exit_code, out, err)

        run(client, f"rm -rf {remote_train_root} && mkdir -p {remote_source_root} {remote_data_root} {remote_output_root}")
        upload_tree(sftp, args.local_project_root / "train", posixpath.join(remote_source_root, "train"))
        upload_tree(sftp, args.local_project_root / "backend" / "app", posixpath.join(remote_source_root, "backend/app"))
        upload_tree(sftp, args.local_data_dir, remote_data_root)

        train_command = (
            f"cd {remote_source_root}/train && "
            "python3 train_text_fusion.py "
            f"--input-dir {remote_data_root} "
            f"--output-dir {remote_output_root} "
            f"--epochs {args.epochs} "
            f"--batch-size {args.batch_size} "
            "--multi-gpu --mixed-precision"
        )
        exit_code, stdout, stderr = run(client, f"CUDA_VISIBLE_DEVICES=0,1 {train_command}")

        write_text(args.local_output_dir / "remote_stop_start.log", "".join(stop_logs))
        write_text(args.local_output_dir / "remote_train_stdout.log", stdout)
        write_text(args.local_output_dir / "remote_train_stderr.log", stderr)

        if exit_code != 0:
            raise SystemExit(f"Remote training failed with exit code {exit_code}. Check the downloaded logs.")

        download_tree(sftp, remote_output_root, args.local_output_dir / "model_output")
        download_tree(sftp, remote_data_root, args.local_output_dir / "server_data_copy")
    finally:
        run(client, f"rm -rf {remote_train_root}")
        start_logs: list[str] = []
        start_commands: list[str] = []
        if service_states.get("cosyvoice-tts.service"):
            start_commands.extend(
                [
                    "systemctl start cosyvoice-tts.service || true",
                    "systemctl status cosyvoice-tts.service --no-pager | head -n 20 || true",
                ]
            )
        if service_states.get("qwen-vllm.service"):
            start_commands.extend(
                [
                    "systemctl start qwen-vllm.service || true",
                    "systemctl status qwen-vllm.service --no-pager | head -n 20 || true",
                ]
            )
        start_commands.append("nvidia-smi")
        for command in start_commands:
            exit_code, out, err = run(client, command)
            append_log(start_logs, command, exit_code, out, err)

        existing_log = (
            (args.local_output_dir / "remote_stop_start.log").read_text(encoding="utf-8")
            if (args.local_output_dir / "remote_stop_start.log").exists()
            else "".join(stop_logs)
        )
        write_text(args.local_output_dir / "remote_stop_start.log", existing_log + "\n".join(start_logs))
        sftp.close()
        client.close()

    print(
        "Remote dual-GPU training completed. Results were downloaded locally, remote temp files were removed, "
        "and services were restored."
    )


if __name__ == "__main__":
    main()
