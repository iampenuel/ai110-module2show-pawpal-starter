"""PawPal+ core domain model and scheduling engine.

This module holds the framework-agnostic logic for PawPal+. It defines the
domain objects (:class:`Task`, :class:`Pet`, :class:`Owner`), the
:class:`Scheduler` that reasons across every pet an owner has, and JSON
persistence helpers (:func:`save_to_json` / :func:`load_from_json`).

No Streamlit or CLI code lives here so the same logic can power the Streamlit
app (``app.py``), the CLI demo (``main.py``) and the test suite.

The Scheduler's query methods return :class:`ScheduleEntry` objects — a small
record pairing a ``Task`` with the ``Pet`` it belongs to — so callers always
know which pet a task came from when tasks are mixed across pets.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

# ---------------------------------------------------------------------------
# Validation vocabularies. Centralised so every layer agrees on the rules.
# ---------------------------------------------------------------------------
VALID_PRIORITIES: tuple[str, ...] = ("low", "medium", "high")
VALID_FREQUENCIES: tuple[str, ...] = ("once", "daily", "weekly")

# Lower rank sorts first: high-priority tasks come before low-priority ones.
_PRIORITY_RANK: dict[str, int] = {"high": 0, "medium": 1, "low": 2}

# Default granularity for the next-available-slot search, in minutes.
DEFAULT_SLOT_INCREMENT_MINUTES: int = 15


def _new_task_id() -> str:
    """Return a short, stable, unique identifier suitable for persistence."""
    return uuid.uuid4().hex[:12]


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------
@dataclass
class Task:
    """A single pet-care task such as a walk, feeding or vet visit.

    A task occupies the half-open time range ``[due_at, due_at + duration)``.
    """

    description: str
    due_at: datetime
    duration_minutes: int
    priority: str = "medium"
    frequency: str = "once"
    completed: bool = False
    task_id: str = field(default_factory=_new_task_id)

    def __post_init__(self) -> None:
        """Validate the task's fields, raising ``ValueError`` on bad input."""
        if not self.description or not self.description.strip():
            raise ValueError("Task description must be a non-empty string.")
        self.description = self.description.strip()

        if not isinstance(self.due_at, datetime):
            raise ValueError("Task due_at must be a datetime instance.")

        if self.duration_minutes <= 0:
            raise ValueError("Task duration_minutes must be a positive integer.")

        if self.priority not in VALID_PRIORITIES:
            raise ValueError(
                f"Invalid priority {self.priority!r}; expected one of {VALID_PRIORITIES}."
            )

        if self.frequency not in VALID_FREQUENCIES:
            raise ValueError(
                f"Invalid frequency {self.frequency!r}; expected one of {VALID_FREQUENCIES}."
            )

        if not self.task_id:
            self.task_id = _new_task_id()

    def end_time(self) -> datetime:
        """Return when the task finishes (``due_at`` plus its duration)."""
        return self.due_at + timedelta(minutes=self.duration_minutes)

    def mark_complete(self) -> None:
        """Mark this task as completed."""
        self.completed = True

    def overlaps(self, other: "Task") -> bool:
        """Return ``True`` if this task's time range overlaps ``other``'s.

        Uses half-open ranges so back-to-back tasks (one ends exactly when the
        next begins) do **not** count as a conflict.
        """
        return self.due_at < other.end_time() and other.due_at < self.end_time()

    def create_next_occurrence(self) -> Optional["Task"]:
        """Build the next occurrence of a recurring task.

        Returns a fresh, incomplete :class:`Task` (with a new ``task_id``) for
        ``daily``/``weekly`` tasks, or ``None`` for one-time (``once``) tasks.
        Description, duration, priority and frequency are preserved.
        """
        if self.frequency == "daily":
            step = timedelta(days=1)
        elif self.frequency == "weekly":
            step = timedelta(days=7)
        else:  # "once" — nothing to repeat
            return None

        return Task(
            description=self.description,
            due_at=self.due_at + step,
            duration_minutes=self.duration_minutes,
            priority=self.priority,
            frequency=self.frequency,
            completed=False,
        )

    def to_dict(self) -> dict:
        """Serialise the task to a JSON-friendly dict (ISO 8601 datetime)."""
        return {
            "task_id": self.task_id,
            "description": self.description,
            "due_at": self.due_at.isoformat(),
            "duration_minutes": self.duration_minutes,
            "priority": self.priority,
            "frequency": self.frequency,
            "completed": self.completed,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        """Rebuild a :class:`Task` from a dict produced by :meth:`to_dict`."""
        return cls(
            description=data["description"],
            due_at=datetime.fromisoformat(data["due_at"]),
            duration_minutes=int(data["duration_minutes"]),
            priority=data.get("priority", "medium"),
            frequency=data.get("frequency", "once"),
            completed=bool(data.get("completed", False)),
            task_id=data.get("task_id", "") or _new_task_id(),
        )


# ---------------------------------------------------------------------------
# Pet
# ---------------------------------------------------------------------------
@dataclass
class Pet:
    """A pet that owns a collection of care tasks."""

    name: str
    species: str
    age: Optional[int] = None
    notes: str = ""
    tasks: list[Task] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("Pet name must be a non-empty string.")
        self.name = self.name.strip()

    def add_task(self, task: Task) -> Task:
        """Append a task to this pet and return it."""
        if not isinstance(task, Task):
            raise ValueError("add_task expects a Task instance.")
        self.tasks.append(task)
        return task

    def list_tasks(self) -> list[Task]:
        """Return a shallow copy of this pet's task list."""
        return list(self.tasks)

    def get_task(self, task_id: str) -> Task:
        """Return the task with ``task_id`` or raise ``KeyError`` if absent."""
        for task in self.tasks:
            if task.task_id == task_id:
                return task
        raise KeyError(f"No task with id {task_id!r} for pet {self.name!r}.")

    def remove_task(self, task_id: str) -> Task:
        """Remove and return the task with ``task_id`` (``KeyError`` if absent)."""
        task = self.get_task(task_id)
        self.tasks.remove(task)
        return task

    def to_dict(self) -> dict:
        """Serialise the pet (and its tasks) to a JSON-friendly dict."""
        return {
            "name": self.name,
            "species": self.species,
            "age": self.age,
            "notes": self.notes,
            "tasks": [task.to_dict() for task in self.tasks],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Pet":
        """Rebuild a :class:`Pet` (and its tasks) from a dict."""
        return cls(
            name=data["name"],
            species=data.get("species", ""),
            age=data.get("age"),
            notes=data.get("notes", ""),
            tasks=[Task.from_dict(t) for t in data.get("tasks", [])],
        )


# ---------------------------------------------------------------------------
# Owner
# ---------------------------------------------------------------------------
@dataclass
class Owner:
    """A pet owner who can have many pets."""

    name: str
    contact: str = ""
    pets: list[Pet] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("Owner name must be a non-empty string.")
        self.name = self.name.strip()

    def add_pet(self, pet: Pet) -> Pet:
        """Add a pet to this owner and return it."""
        if not isinstance(pet, Pet):
            raise ValueError("add_pet expects a Pet instance.")
        self.pets.append(pet)
        return pet

    def get_pet(self, name: str) -> Pet:
        """Return the pet matching ``name`` (case-insensitive) or ``KeyError``."""
        for pet in self.pets:
            if pet.name.lower() == name.strip().lower():
                return pet
        raise KeyError(f"No pet named {name!r} for owner {self.name!r}.")

    def list_pets(self) -> list[Pet]:
        """Return a shallow copy of this owner's pet list."""
        return list(self.pets)

    def get_all_tasks(self) -> list[Task]:
        """Return every task across all of this owner's pets (flattened)."""
        return [task for pet in self.pets for task in pet.tasks]

    def to_dict(self) -> dict:
        """Serialise the owner (and the full pet/task tree) to a dict."""
        return {
            "name": self.name,
            "contact": self.contact,
            "pets": [pet.to_dict() for pet in self.pets],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Owner":
        """Rebuild a full :class:`Owner` object graph from a dict."""
        return cls(
            name=data["name"],
            contact=data.get("contact", ""),
            pets=[Pet.from_dict(p) for p in data.get("pets", [])],
        )


# ---------------------------------------------------------------------------
# Scheduler return types
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ScheduleEntry:
    """A task paired with the pet it belongs to.

    Returned by Scheduler queries so callers always know which pet a task came
    from, even when tasks from several pets are merged into one list.
    """

    pet: Pet
    task: Task


@dataclass(frozen=True)
class Conflict:
    """Two overlapping schedule entries and the window they share."""

    first: ScheduleEntry
    second: ScheduleEntry
    overlap_start: datetime
    overlap_end: datetime

    def describe(self) -> str:
        """Return a human-readable one-line summary of the conflict."""
        start = self.overlap_start.strftime("%Y-%m-%d %H:%M")
        end = self.overlap_end.strftime("%H:%M")
        return (
            f"{self.first.pet.name}'s '{self.first.task.description}' overlaps "
            f"{self.second.pet.name}'s '{self.second.task.description}' "
            f"({start}–{end})"
        )


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------
class Scheduler:
    """Reasons about tasks across *all* of an owner's pets.

    The scheduler never owns task data itself; it always reads live from the
    owner's pets, so any change to a pet's tasks is reflected immediately.
    Query methods return new lists and never mutate the pets' task lists.
    """

    def __init__(self, owner: Owner) -> None:
        self.owner = owner

    def get_all_tasks(self) -> list[ScheduleEntry]:
        """Return a :class:`ScheduleEntry` for every task across every pet."""
        return [
            ScheduleEntry(pet=pet, task=task)
            for pet in self.owner.pets
            for task in pet.tasks
        ]

    def sort_by_due_time(self) -> list[ScheduleEntry]:
        """Return all entries sorted chronologically by ``due_at``.

        Deterministic and non-mutating: ties break by pet name then
        description so equal due-times always sort the same way.
        """
        return sorted(
            self.get_all_tasks(),
            key=lambda e: (e.task.due_at, e.pet.name, e.task.description),
        )

    def filter_tasks(
        self,
        pet_name: Optional[str] = None,
        completed: Optional[bool] = None,
        priority: Optional[str] = None,
        on_date: Optional[datetime] = None,
    ) -> list[ScheduleEntry]:
        """Return entries matching every supplied (non-``None``) criterion.

        Filters combine with AND. ``on_date`` accepts a ``datetime`` or
        ``date`` and matches tasks whose ``due_at`` falls on that calendar day.
        Works across all pets.
        """
        if priority is not None and priority not in VALID_PRIORITIES:
            raise ValueError(
                f"Invalid priority {priority!r}; expected one of {VALID_PRIORITIES}."
            )

        target_date = None
        if on_date is not None:
            target_date = on_date.date() if isinstance(on_date, datetime) else on_date

        results: list[ScheduleEntry] = []
        for entry in self.sort_by_due_time():
            if pet_name is not None and entry.pet.name.lower() != pet_name.strip().lower():
                continue
            if completed is not None and entry.task.completed != completed:
                continue
            if priority is not None and entry.task.priority != priority:
                continue
            if target_date is not None and entry.task.due_at.date() != target_date:
                continue
            results.append(entry)
        return results

    def detect_conflicts(self) -> list[Conflict]:
        """Return every pair of time-overlapping tasks across all pets.

        Two tasks conflict when their ``[due_at, end_time)`` ranges overlap,
        even by a minute and even when they belong to different pets. Tasks
        that merely touch end-to-start are not conflicts.
        """
        entries = self.sort_by_due_time()
        conflicts: list[Conflict] = []
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                a, b = entries[i], entries[j]
                if a.task.overlaps(b.task):
                    conflicts.append(
                        Conflict(
                            first=a,
                            second=b,
                            overlap_start=max(a.task.due_at, b.task.due_at),
                            overlap_end=min(a.task.end_time(), b.task.end_time()),
                        )
                    )
        return conflicts

    def complete_task(self, task_id: str) -> Optional[Task]:
        """Complete the task with ``task_id`` and spawn its next occurrence.

        Marks the task complete. For ``daily``/``weekly`` tasks, a new
        incomplete occurrence is created and added to the *same* pet, then
        returned. Returns ``None`` for one-time tasks. If the task is already
        completed, this is a no-op that returns ``None`` — so calling it twice
        never duplicates a recurrence. Raises ``KeyError`` if no task matches.
        """
        for pet in self.owner.pets:
            for task in pet.tasks:
                if task.task_id == task_id:
                    if task.completed:
                        return None  # idempotent: no duplicate recurrence
                    task.mark_complete()
                    next_task = task.create_next_occurrence()
                    if next_task is not None:
                        pet.add_task(next_task)
                    return next_task
        raise KeyError(f"No task with id {task_id!r} for owner {self.owner.name!r}.")

    def sort_by_priority_and_time(self) -> list[ScheduleEntry]:
        """Return entries ordered by priority (high→low), then by due time.

        Within the same priority, earlier tasks come first. Works across pets.
        """
        return sorted(
            self.get_all_tasks(),
            key=lambda e: (
                _PRIORITY_RANK[e.task.priority],
                e.task.due_at,
                e.pet.name,
                e.task.description,
            ),
        )

    def find_next_available_slot(
        self,
        duration_minutes: int,
        search_start: datetime,
        search_end: datetime,
        increment_minutes: int = DEFAULT_SLOT_INCREMENT_MINUTES,
    ) -> Optional[datetime]:
        """Find the earliest free slot of ``duration_minutes`` in a window.

        Scans candidate start times from ``search_start`` toward
        ``search_end`` in ``increment_minutes`` steps and returns the first
        start time whose ``[start, start+duration)`` range overlaps no
        incomplete task across any pet. Returns ``None`` when the window has no
        room. Completed tasks are ignored — they no longer occupy time.
        """
        if duration_minutes <= 0:
            raise ValueError("duration_minutes must be positive.")
        if increment_minutes <= 0:
            raise ValueError("increment_minutes must be positive.")
        if search_end <= search_start:
            return None

        step = timedelta(minutes=increment_minutes)
        slot_length = timedelta(minutes=duration_minutes)
        busy = [
            entry.task
            for entry in self.get_all_tasks()
            if not entry.task.completed
        ]

        candidate = search_start
        while candidate + slot_length <= search_end:
            candidate_end = candidate + slot_length
            clash = any(
                candidate < t.end_time() and t.due_at < candidate_end for t in busy
            )
            if not clash:
                return candidate
            candidate += step
        return None


# ---------------------------------------------------------------------------
# JSON persistence (standard library only)
# ---------------------------------------------------------------------------
def save_to_json(owner: Owner, path: str) -> None:
    """Persist an :class:`Owner` (and its full pet/task tree) to ``path``.

    Datetimes are stored as ISO 8601 strings. Completion status, frequency,
    priority, duration and stable task IDs are all preserved.
    """
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(owner.to_dict(), fh, indent=2)


def load_from_json(path: str) -> Owner:
    """Load an :class:`Owner` previously saved with :func:`save_to_json`.

    Raises ``FileNotFoundError`` with a clear message if ``path`` is missing,
    and ``ValueError`` if the file is not valid PawPal+ JSON.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"No PawPal+ save file at {path!r}.") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Save file {path!r} is not valid JSON: {exc}") from exc

    if not isinstance(data, dict) or "name" not in data:
        raise ValueError(f"Save file {path!r} is not a valid PawPal+ owner record.")

    return Owner.from_dict(data)
