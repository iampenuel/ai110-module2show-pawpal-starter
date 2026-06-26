"""PawPal+ command-line demonstration.

Runs a scripted scenario that exercises every feature of the PawPal+ engine
in ``pawpal_system.py`` and prints readable, formatted output. Run it with::

    python main.py

All formatting uses the standard library only (no extra dependencies).
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta

from pawpal_system import (
    Conflict,
    Owner,
    Pet,
    ScheduleEntry,
    Scheduler,
    Task,
    load_from_json,
    save_to_json,
)

# Fixed reference day so the demo output is reproducible run-to-run.
DAY = datetime(2026, 7, 1, 0, 0)

PRIORITY_ICON = {"high": "🔴", "medium": "🟡", "low": "🟢"}


def heading(title: str) -> None:
    """Print a clear section heading."""
    print()
    print("=" * 64)
    print(f"  {title}")
    print("=" * 64)


def format_table(rows: list[list[str]], headers: list[str]) -> str:
    """Render aligned, fixed-width columns from string rows (stdlib only)."""
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt(cells: list[str]) -> str:
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells))

    line = "-+-".join("-" * w for w in widths)
    out = [fmt(headers), line]
    out.extend(fmt(row) for row in rows)
    return "\n".join(out)


def entry_row(entry: ScheduleEntry) -> list[str]:
    """Turn a ScheduleEntry into a row of display strings."""
    t = entry.task
    status = "✅ done" if t.completed else "⬜ open"
    return [
        t.due_at.strftime("%a %m-%d %H:%M"),
        f"{t.duration_minutes}m",
        f"{PRIORITY_ICON[t.priority]} {t.priority}",
        t.frequency,
        entry.pet.name,
        t.description,
        status,
    ]


def print_schedule(entries: list[ScheduleEntry], title: str) -> None:
    """Print a list of schedule entries as a formatted table."""
    print(f"\n{title}")
    if not entries:
        print("  (no matching tasks)")
        return
    headers = ["When", "Dur", "Priority", "Freq", "Pet", "Task", "Status"]
    rows = [entry_row(e) for e in entries]
    print(format_table(rows, headers))


def build_scenario() -> Owner:
    """Create an owner with two pets and five tasks (added out of order)."""
    owner = Owner(name="Jordan Rivera", contact="jordan@example.com")

    mochi = owner.add_pet(Pet(name="Mochi", species="dog", age=3, notes="High energy"))
    biscuit = owner.add_pet(Pet(name="Biscuit", species="cat", age=7, notes="Senior"))

    # Tasks are deliberately added out of chronological order.
    mochi.add_task(Task("Evening walk", DAY.replace(hour=18, minute=0), 30, "high", "daily"))
    mochi.add_task(Task("Morning walk", DAY.replace(hour=8, minute=0), 30, "high", "daily"))
    mochi.add_task(Task("Bath", DAY.replace(hour=8, minute=15), 45, "low", "weekly"))

    biscuit.add_task(Task("Give medication", DAY.replace(hour=8, minute=20), 10, "high", "daily"))
    biscuit.add_task(Task("Brush coat", DAY.replace(hour=12, minute=0), 20, "medium", "once"))

    return owner


def main() -> None:
    owner = build_scenario()
    scheduler = Scheduler(owner)

    heading("1. Owner & Pets")
    print(f"👤 Owner: {owner.name}  ({owner.contact})")
    for pet in owner.list_pets():
        age = f"{pet.age}y" if pet.age is not None else "age n/a"
        print(f"   🐾 {pet.name} — {pet.species}, {age}, {len(pet.tasks)} tasks  [{pet.notes}]")

    heading("2. Task Addition (insertion order, per pet)")
    for pet in owner.list_pets():
        print(f"\n{pet.name}:")
        for task in pet.list_tasks():
            print(f"   • {task.description} @ {task.due_at.strftime('%H:%M')} ({task.priority})")

    heading("3. Chronological Sorting (across all pets)")
    print_schedule(scheduler.sort_by_due_time(), "Sorted by due time:")

    heading("4. Filtering")
    print_schedule(
        scheduler.filter_tasks(priority="high"),
        "High-priority tasks across all pets:",
    )
    print_schedule(
        scheduler.filter_tasks(pet_name="Biscuit"),
        "Tasks for Biscuit only:",
    )

    heading("5. Conflict Detection (duration-based overlap)")
    conflicts: list[Conflict] = scheduler.detect_conflicts()
    if conflicts:
        for c in conflicts:
            print(f"   ⚠️  {c.describe()}")
    else:
        print("   ✅ No conflicts found.")

    heading("6. Priority-First Scheduling")
    print_schedule(
        scheduler.sort_by_priority_and_time(),
        "Sorted by priority (high→low), then time:",
    )

    heading("7. Recurring-Task Completion")
    target = scheduler.filter_tasks(pet_name="Mochi", priority="high")[0]
    print(f"Completing Mochi's daily task: '{target.task.description}' "
          f"({target.task.due_at.strftime('%m-%d %H:%M')})")
    spawned = scheduler.complete_task(target.task.task_id)
    if spawned:
        print(f"   ↪ next occurrence created: '{spawned.description}' "
              f"on {spawned.due_at.strftime('%a %m-%d %H:%M')} (completed={spawned.completed})")
    print("Calling complete_task again on the same id (idempotency check):")
    repeat = scheduler.complete_task(target.task.task_id)
    print(f"   ↪ returned {repeat!r} — no duplicate recurrence created.")

    heading("8. Next Available Slot")
    window_start = DAY.replace(hour=8, minute=0)
    window_end = DAY.replace(hour=20, minute=0)
    slot = scheduler.find_next_available_slot(60, window_start, window_end)
    if slot:
        print(f"   📅 Earliest free 60-minute slot between 08:00 and 20:00: "
              f"{slot.strftime('%a %m-%d %H:%M')}")
    else:
        print("   ❌ No free 60-minute slot in the window.")

    heading("9. JSON Save / Load Round-Trip")
    tmp_dir = tempfile.mkdtemp(prefix="pawpal_demo_")
    save_path = os.path.join(tmp_dir, "owner.json")
    save_to_json(owner, save_path)
    print(f"   💾 Saved owner to temporary file: {save_path}")
    reloaded = load_from_json(save_path)
    print(f"   📂 Reloaded owner: {reloaded.name} with {len(reloaded.pets)} pets "
          f"and {len(reloaded.get_all_tasks())} tasks.")
    match = (
        reloaded.name == owner.name
        and len(reloaded.get_all_tasks()) == len(owner.get_all_tasks())
    )
    print(f"   {'✅' if match else '❌'} Round-trip preserved owner, pets and tasks.")
    os.remove(save_path)
    os.rmdir(tmp_dir)

    print()
    print("PawPal+ demo complete. 🐾")


if __name__ == "__main__":
    main()
