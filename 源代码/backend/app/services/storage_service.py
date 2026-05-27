# 微博方向社交机器人检测V1.0

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from typing import Iterator

from app.core.config import get_settings
from app.schemas import DetectionReport, ReportListItem, SystemSettingsPayload


settings = get_settings()


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(settings.database_path)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def initialize_database() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
                report_id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                created_at TEXT NOT NULL,
                final_probability REAL NOT NULL,
                risk_level TEXT NOT NULL,
                final_label TEXT NOT NULL,
                summary TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS training_runs (
                run_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )


def save_report(report: DetectionReport) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO reports (
                report_id,
                username,
                created_at,
                final_probability,
                risk_level,
                final_label,
                summary,
                payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report.report_id,
                report.username,
                report.created_at.isoformat(),
                report.scores.final_probability,
                report.scores.risk_level,
                report.scores.final_label,
                report.summary,
                report.model_dump_json(),
            ),
        )


def list_reports(limit: int = 20) -> list[ReportListItem]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT report_id, created_at, username, final_label, risk_level, final_probability, summary
            FROM reports
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [ReportListItem(**dict(row)) for row in rows]


def get_report(report_id: str) -> DetectionReport | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT payload FROM reports WHERE report_id = ?",
            (report_id,),
        ).fetchone()
    if row is None:
        return None
    return DetectionReport.model_validate_json(row["payload"])


def get_report_statistics() -> dict[str, float | int]:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                COUNT(*) AS total_reports,
                SUM(CASE WHEN risk_level = '高风险' THEN 1 ELSE 0 END) AS high_risk_reports,
                AVG(final_probability) AS average_probability
            FROM reports
            """
        ).fetchone()
    return {
        "total_reports": int(row["total_reports"] or 0),
        "high_risk_reports": int(row["high_risk_reports"] or 0),
        "average_probability": float(row["average_probability"] or 0.0),
    }


def save_training_run(run_id: str, created_at: str, payload: dict[str, object]) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO training_runs (run_id, created_at, payload)
            VALUES (?, ?, ?)
            """,
            (run_id, created_at, json.dumps(payload, ensure_ascii=False)),
        )


def get_latest_training_run() -> dict[str, object] | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT payload
            FROM training_runs
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()
    if row is None:
        return None
    return json.loads(row["payload"])


def save_settings(payload: SystemSettingsPayload) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO settings (setting_key, setting_value)
            VALUES (?, ?)
            """,
            ("system_settings", payload.model_dump_json()),
        )


def load_settings() -> SystemSettingsPayload:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT setting_value FROM settings WHERE setting_key = ?",
            ("system_settings",),
        ).fetchone()
    if row is None:
        payload = SystemSettingsPayload(
            bind_host=settings.host,
            bind_port=settings.port,
            default_max_posts=settings.default_max_posts,
        )
        save_settings(payload)
        return payload
    return SystemSettingsPayload.model_validate_json(row["setting_value"])


initialize_database()
