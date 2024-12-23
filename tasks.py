"""
State management for company research as "tasks".

The TaskManager class is designed to be used as a singleton, and the task_manager()
function is provided to get the singleton instance.

This module provides a TaskManager class to create, update, and retrieve tasks.
Tasks are stored in a SQLite database, and the TaskManager class provides methods
to interact with the database.
"""

import json
import logging
import multiprocessing
import os
import sqlite3
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

import models

logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_PATH = os.path.join(HERE, "data", "tasks.db")


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskManager:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self.lock = multiprocessing.Lock()
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    company_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """
            )

    def create_task(self, company_name: str) -> str:
        task_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO tasks (id, company_name, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (task_id, company_name, TaskStatus.PENDING.value, now, now),
                )
        return task_id

    def get_task(self, task_id: str) -> Optional[dict]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()

        if row:
            return {
                "id": row[0],
                "company_name": row[1],
                "status": row[2],
                "result": json.loads(row[3]) if row[3] else None,
                "error": row[4],
                "created_at": row[5],
                "updated_at": row[6],
            }
        return None

    def update_task(
        self, task_id: str, status: TaskStatus, result: dict = None, error: str = None
    ):
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    UPDATE tasks 
                    SET status = ?, result = ?, error = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        status.value,
                        json.dumps(result) if result else None,
                        error,
                        datetime.utcnow().isoformat(),
                        task_id,
                    ),
                )

    def get_next_pending_task(self) -> Optional[tuple[str, str]]:
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    SELECT id, company_name FROM tasks 
                    WHERE status = ? 
                    ORDER BY created_at ASC 
                     LIMIT 1
                    """,
                    (TaskStatus.PENDING.value,),
                )
                row = cursor.fetchone()
        return row


# Module-level singleton
_task_manager = None


def task_manager() -> TaskManager:
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager
