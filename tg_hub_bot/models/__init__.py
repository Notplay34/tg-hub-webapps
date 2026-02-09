from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass
class TaskSummary:
    """
    Краткое представление задачи для напоминаний бота.

    Используется в репозиториях и сервисах, чтобы не работать напрямую
    с «сырыми» dict/Row из БД.
    """

    user_id: str
    title: str
    deadline: str
    priority: str | None = None
    reminder_time: str | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "TaskSummary":
        return cls(
            user_id=str(row["user_id"]),
            title=row["title"],
            deadline=row["deadline"],
            priority=row.get("priority"),
            reminder_time=row.get("reminder_time"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "title": self.title,
            "deadline": self.deadline,
            "priority": self.priority,
            "reminder_time": self.reminder_time,
        }


__all__ = ["TaskSummary"]

