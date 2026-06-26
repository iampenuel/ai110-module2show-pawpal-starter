"""PawPal+ core domain model and scheduling engine (skeleton).

This module will contain the framework-agnostic logic for PawPal+: the
``Task``, ``Pet``, ``Owner`` and ``Scheduler`` classes plus JSON persistence.
No Streamlit code lives here. Implementation follows the skeleton commit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Task:
    """A single pet-care task. Implementation pending."""

    description: str
    due_at: datetime
    duration_minutes: int
    priority: str = "medium"
    frequency: str = "once"
    completed: bool = False
    task_id: str = ""

    def mark_complete(self) -> None:
        raise NotImplementedError

    def create_next_occurrence(self) -> "Task | None":
        raise NotImplementedError

    def end_time(self) -> datetime:
        raise NotImplementedError


@dataclass
class Pet:
    """A pet owned by an Owner. Implementation pending."""

    name: str
    species: str
    tasks: list[Task] = field(default_factory=list)

    def add_task(self, task: Task) -> Task:
        raise NotImplementedError

    def list_tasks(self) -> list[Task]:
        raise NotImplementedError


@dataclass
class Owner:
    """A pet owner who has one or more pets. Implementation pending."""

    name: str
    pets: list[Pet] = field(default_factory=list)

    def add_pet(self, pet: Pet) -> Pet:
        raise NotImplementedError

    def get_all_tasks(self) -> list[Task]:
        raise NotImplementedError


class Scheduler:
    """Manages tasks across all of an Owner's pets. Implementation pending."""

    def __init__(self, owner: Owner) -> None:
        self.owner = owner

    def get_all_tasks(self) -> list:
        raise NotImplementedError

    def sort_by_due_time(self) -> list:
        raise NotImplementedError

    def detect_conflicts(self) -> list:
        raise NotImplementedError
