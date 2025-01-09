"""
State management for company research and other actions as asynhronous"tasks".

The TaskManager class is designed to be used as a singleton, and the task_manager()
function is provided to get the singleton instance.

This module provides a TaskManager class to create, update, and retrieve tasks.
Tasks are stored in a SQLite database, and the TaskManager class provides methods
to interact with the database.

Why not use a task queue eg Celery or distributed queue like RabbitMQ?
- It's more infrastructure and complexity than we need
- We aren't concerned about volume
- Queues force you to solve for visibility, retries, transactionality, etc
- Using a simple database gives you visibility and transactions for free
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

logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_PATH = os.path.join(HERE, "data", "tasks.db")


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskType(Enum):
    COMPANY_RESEARCH = "company_research"
    GENERATE_REPLY = "generate_reply"


class TaskManager:

    def __init__(self, db_path: str = DEFAULT_DB_PATH, reset_db: bool = False):
        self.db_path = db_path
        self.lock = multiprocessing.Lock()
        self._init_db(reset_db)

    def _init_db(self, reset_db: bool = False):
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                if reset_db:
                    logger.info("Deleting existing tasks table if it exists")
                    conn.execute("DROP TABLE IF EXISTS tasks")
                logger.info("Creating tasks table if it doesn't exist")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    args TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """
                )

    def create_task(self, task_type: TaskType, args: dict) -> str:
        task_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO tasks (id, type, args, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task_id,
                        task_type.value,
                        json.dumps(args),
                        TaskStatus.PENDING.value,
                        now,
                        now,
                    ),
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
                "type": TaskType(row[1]),
                "args": json.loads(row[2]),
                "status": TaskStatus(row[3]),
                "result": json.loads(row[4]) if row[4] else None,
                "error": row[5],
                "created_at": row[6],
                "updated_at": row[7],
            }
        return None

    def update_task(
        self,
        task_id: str,
        status: TaskStatus,
        result: Optional[dict] = None,
        error: str = "",
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

    def get_next_pending_task(self) -> Optional[tuple[str, TaskType, dict]]:
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    SELECT id, type, args FROM tasks 
                    WHERE status = ? 
                    ORDER BY created_at ASC 
                     LIMIT 1
                    """,
                    (TaskStatus.PENDING.value,),
                )
                row = cursor.fetchone()
                if row is None:
                    return None
                task_id, task_type, task_args = row
                task_id = str(task_id)
                task_type = TaskType(task_type)
                task_args = json.loads(task_args)
                assert isinstance(task_args, dict)
                return task_id, task_type, task_args


# Module-level singleton
_task_manager = None


def task_manager() -> TaskManager:
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--reset-db", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    TaskManager(reset_db=args.reset_db)
