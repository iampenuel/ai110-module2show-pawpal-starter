"""Deterministic pytest suite for the PawPal+ engine (``pawpal_system.py``).

Covers core classes, the required scheduling algorithms, recurrence, the
stretch algorithms, JSON persistence, and validation/edge cases.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from pawpal_system import (
    Owner,
    Pet,
    Scheduler,
    Task,
    load_from_json,
    save_to_json,
)

# A fixed clock keeps every test reproducible.
BASE = datetime(2026, 7, 1, 8, 0)


def make_task(desc="Walk", offset_min=0, duration=30, priority="medium", frequency="once"):
    """Helper to build a task at a fixed offset from BASE."""
    return Task(
        description=desc,
        due_at=BASE + timedelta(minutes=offset_min),
        duration_minutes=duration,
        priority=priority,
        frequency=frequency,
    )


@pytest.fixture
def owner_with_pets():
    """Owner with two pets and a small spread of tasks across both."""
    owner = Owner(name="Jordan")
    mochi = owner.add_pet(Pet(name="Mochi", species="dog"))
    biscuit = owner.add_pet(Pet(name="Biscuit", species="cat"))
    # Out of order on purpose.
    mochi.add_task(make_task("Evening walk", offset_min=600, priority="high"))
    mochi.add_task(make_task("Morning walk", offset_min=0, priority="high", frequency="daily"))
    biscuit.add_task(make_task("Medication", offset_min=120, priority="low", frequency="weekly"))
    return owner


# ---------------------------------------------------------------------------
# Core classes
# ---------------------------------------------------------------------------
def test_task_creation_sets_fields():
    t = make_task("Feed", duration=10, priority="high")
    assert t.description == "Feed"
    assert t.duration_minutes == 10
    assert t.priority == "high"
    assert t.completed is False
    assert t.task_id  # auto-generated, non-empty


def test_task_end_time():
    t = make_task(duration=45)
    assert t.end_time() == BASE + timedelta(minutes=45)


def test_task_completion_changes_status():
    t = make_task()
    assert t.completed is False
    t.mark_complete()
    assert t.completed is True


def test_pet_add_task_grows_collection():
    pet = Pet(name="Mochi", species="dog")
    assert pet.list_tasks() == []
    pet.add_task(make_task("A"))
    pet.add_task(make_task("B"))
    assert len(pet.list_tasks()) == 2


def test_pet_get_and_remove_task():
    pet = Pet(name="Mochi", species="dog")
    t = pet.add_task(make_task("Walk"))
    assert pet.get_task(t.task_id) is t
    removed = pet.remove_task(t.task_id)
    assert removed is t
    assert pet.list_tasks() == []


def test_pet_get_missing_task_raises_keyerror():
    pet = Pet(name="Mochi", species="dog")
    with pytest.raises(KeyError):
        pet.get_task("nope")


def test_owner_add_and_get_pet():
    owner = Owner(name="Jordan")
    owner.add_pet(Pet(name="Mochi", species="dog"))
    owner.add_pet(Pet(name="Biscuit", species="cat"))
    assert len(owner.list_pets()) == 2
    assert owner.get_pet("biscuit").species == "cat"  # case-insensitive


def test_owner_get_missing_pet_raises_keyerror():
    owner = Owner(name="Jordan")
    with pytest.raises(KeyError):
        owner.get_pet("Ghost")


def test_owner_get_all_tasks_across_pets(owner_with_pets):
    assert len(owner_with_pets.get_all_tasks()) == 3


def test_scheduler_collects_tasks_from_multiple_pets(owner_with_pets):
    sched = Scheduler(owner_with_pets)
    entries = sched.get_all_tasks()
    assert len(entries) == 3
    pet_names = {e.pet.name for e in entries}
    assert pet_names == {"Mochi", "Biscuit"}


# ---------------------------------------------------------------------------
# Required algorithms
# ---------------------------------------------------------------------------
def test_sort_by_due_time_is_chronological(owner_with_pets):
    sched = Scheduler(owner_with_pets)
    entries = sched.sort_by_due_time()
    times = [e.task.due_at for e in entries]
    assert times == sorted(times)
    assert entries[0].task.description == "Morning walk"


def test_sort_by_due_time_does_not_mutate_pets(owner_with_pets):
    sched = Scheduler(owner_with_pets)
    before = [t.description for t in owner_with_pets.pets[0].tasks]
    sched.sort_by_due_time()
    after = [t.description for t in owner_with_pets.pets[0].tasks]
    assert before == after


def test_filter_by_pet(owner_with_pets):
    sched = Scheduler(owner_with_pets)
    entries = sched.filter_tasks(pet_name="Biscuit")
    assert len(entries) == 1
    assert entries[0].task.description == "Medication"


def test_filter_by_completion_status(owner_with_pets):
    sched = Scheduler(owner_with_pets)
    target = sched.sort_by_due_time()[0].task
    target.mark_complete()
    assert len(sched.filter_tasks(completed=True)) == 1
    assert len(sched.filter_tasks(completed=False)) == 2


def test_filter_by_priority(owner_with_pets):
    sched = Scheduler(owner_with_pets)
    assert len(sched.filter_tasks(priority="high")) == 2
    assert len(sched.filter_tasks(priority="low")) == 1


def test_filter_invalid_priority_raises(owner_with_pets):
    sched = Scheduler(owner_with_pets)
    with pytest.raises(ValueError):
        sched.filter_tasks(priority="urgent")


def test_filter_combines_pet_and_priority(owner_with_pets):
    sched = Scheduler(owner_with_pets)
    entries = sched.filter_tasks(pet_name="Mochi", priority="high")
    assert len(entries) == 2
    assert all(e.pet.name == "Mochi" for e in entries)


def test_conflict_detection_exact_overlap():
    owner = Owner(name="Jordan")
    pet = owner.add_pet(Pet(name="Mochi", species="dog"))
    pet.add_task(make_task("A", offset_min=0, duration=30))
    pet.add_task(make_task("B", offset_min=0, duration=30))  # identical time
    conflicts = Scheduler(owner).detect_conflicts()
    assert len(conflicts) == 1


def test_conflict_detection_partial_overlap_across_pets():
    owner = Owner(name="Jordan")
    mochi = owner.add_pet(Pet(name="Mochi", species="dog"))
    biscuit = owner.add_pet(Pet(name="Biscuit", species="cat"))
    mochi.add_task(make_task("Walk", offset_min=0, duration=30))     # 08:00-08:30
    biscuit.add_task(make_task("Vet", offset_min=15, duration=30))   # 08:15-08:45
    conflicts = Scheduler(owner).detect_conflicts()
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c.overlap_start == BASE + timedelta(minutes=15)
    assert c.overlap_end == BASE + timedelta(minutes=30)


def test_no_false_conflict_for_adjacent_tasks():
    owner = Owner(name="Jordan")
    pet = owner.add_pet(Pet(name="Mochi", species="dog"))
    pet.add_task(make_task("A", offset_min=0, duration=30))    # 08:00-08:30
    pet.add_task(make_task("B", offset_min=30, duration=30))   # 08:30-09:00
    assert Scheduler(owner).detect_conflicts() == []


# ---------------------------------------------------------------------------
# Recurrence
# ---------------------------------------------------------------------------
def test_daily_recurrence_creates_next_day():
    t = make_task(frequency="daily")
    nxt = t.create_next_occurrence()
    assert nxt is not None
    assert nxt.due_at == t.due_at + timedelta(days=1)
    assert nxt.completed is False
    assert nxt.task_id != t.task_id


def test_weekly_recurrence_creates_seven_days_later():
    t = make_task(frequency="weekly")
    nxt = t.create_next_occurrence()
    assert nxt.due_at == t.due_at + timedelta(days=7)


def test_once_task_does_not_recur():
    t = make_task(frequency="once")
    assert t.create_next_occurrence() is None


def test_complete_task_spawns_recurrence_on_same_pet(owner_with_pets):
    sched = Scheduler(owner_with_pets)
    daily = next(e for e in sched.get_all_tasks() if e.task.frequency == "daily")
    pet = daily.pet
    before = len(pet.tasks)
    spawned = sched.complete_task(daily.task.task_id)
    assert spawned is not None
    assert len(pet.tasks) == before + 1
    assert daily.task.completed is True


def test_completing_twice_does_not_duplicate_recurrence(owner_with_pets):
    sched = Scheduler(owner_with_pets)
    daily = next(e for e in sched.get_all_tasks() if e.task.frequency == "daily")
    pet = daily.pet
    sched.complete_task(daily.task.task_id)
    count_after_first = len(pet.tasks)
    second = sched.complete_task(daily.task.task_id)
    assert second is None
    assert len(pet.tasks) == count_after_first


def test_complete_unknown_task_raises_keyerror(owner_with_pets):
    sched = Scheduler(owner_with_pets)
    with pytest.raises(KeyError):
        sched.complete_task("does-not-exist")


# ---------------------------------------------------------------------------
# Stretch: priority sorting, next slot, persistence
# ---------------------------------------------------------------------------
def test_priority_first_sorting_across_pets():
    owner = Owner(name="Jordan")
    mochi = owner.add_pet(Pet(name="Mochi", species="dog"))
    biscuit = owner.add_pet(Pet(name="Biscuit", species="cat"))
    mochi.add_task(make_task("Low early", offset_min=0, priority="low"))
    biscuit.add_task(make_task("High late", offset_min=300, priority="high"))
    mochi.add_task(make_task("Medium mid", offset_min=120, priority="medium"))
    order = [e.task.priority for e in Scheduler(owner).sort_by_priority_and_time()]
    assert order == ["high", "medium", "low"]


def test_priority_sort_breaks_ties_by_time():
    owner = Owner(name="Jordan")
    pet = owner.add_pet(Pet(name="Mochi", species="dog"))
    pet.add_task(make_task("Later high", offset_min=120, priority="high"))
    pet.add_task(make_task("Earlier high", offset_min=0, priority="high"))
    entries = Scheduler(owner).sort_by_priority_and_time()
    assert entries[0].task.description == "Earlier high"


def test_find_next_available_slot_in_open_window():
    owner = Owner(name="Jordan")
    pet = owner.add_pet(Pet(name="Mochi", species="dog"))
    pet.add_task(make_task("Walk", offset_min=0, duration=30))  # 08:00-08:30
    slot = Scheduler(owner).find_next_available_slot(
        30, BASE, BASE + timedelta(hours=4)
    )
    # 08:00 is busy; next 15-min increment that fits is 08:30.
    assert slot == BASE + timedelta(minutes=30)


def test_find_next_available_slot_skips_occupied_windows():
    owner = Owner(name="Jordan")
    mochi = owner.add_pet(Pet(name="Mochi", species="dog"))
    biscuit = owner.add_pet(Pet(name="Biscuit", species="cat"))
    mochi.add_task(make_task("Walk", offset_min=0, duration=60))    # 08:00-09:00
    biscuit.add_task(make_task("Vet", offset_min=60, duration=60))  # 09:00-10:00
    slot = Scheduler(owner).find_next_available_slot(
        30, BASE, BASE + timedelta(hours=4)
    )
    assert slot == BASE + timedelta(minutes=120)  # 10:00


def test_find_next_available_slot_returns_none_when_full():
    owner = Owner(name="Jordan")
    pet = owner.add_pet(Pet(name="Mochi", species="dog"))
    pet.add_task(make_task("All day", offset_min=0, duration=240))  # 08:00-12:00
    slot = Scheduler(owner).find_next_available_slot(
        30, BASE, BASE + timedelta(hours=4)
    )
    assert slot is None


def test_completed_tasks_do_not_block_slots():
    owner = Owner(name="Jordan")
    pet = owner.add_pet(Pet(name="Mochi", species="dog"))
    t = pet.add_task(make_task("Walk", offset_min=0, duration=240))
    t.mark_complete()
    slot = Scheduler(owner).find_next_available_slot(
        30, BASE, BASE + timedelta(hours=4)
    )
    assert slot == BASE  # completed task no longer occupies time


def test_json_round_trip_preserves_everything(tmp_path, owner_with_pets):
    path = tmp_path / "owner.json"
    save_to_json(owner_with_pets, str(path))
    loaded = load_from_json(str(path))

    assert loaded.name == owner_with_pets.name
    assert len(loaded.pets) == len(owner_with_pets.pets)
    original_tasks = {t.task_id: t for t in owner_with_pets.get_all_tasks()}
    loaded_tasks = {t.task_id: t for t in loaded.get_all_tasks()}
    assert original_tasks.keys() == loaded_tasks.keys()
    for tid, orig in original_tasks.items():
        copy = loaded_tasks[tid]
        assert copy.description == orig.description
        assert copy.due_at == orig.due_at
        assert copy.duration_minutes == orig.duration_minutes
        assert copy.priority == orig.priority
        assert copy.frequency == orig.frequency
        assert copy.completed == orig.completed


def test_load_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_from_json(str(tmp_path / "absent.json"))


def test_load_malformed_json_raises(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{ this is not valid json", encoding="utf-8")
    with pytest.raises(ValueError):
        load_from_json(str(bad))


def test_load_wrong_shape_raises(tmp_path):
    wrong = tmp_path / "wrong.json"
    wrong.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    with pytest.raises(ValueError):
        load_from_json(str(wrong))


# ---------------------------------------------------------------------------
# Validation & edge cases
# ---------------------------------------------------------------------------
def test_invalid_priority_rejected():
    with pytest.raises(ValueError):
        make_task(priority="urgent")


def test_invalid_frequency_rejected():
    with pytest.raises(ValueError):
        make_task(frequency="hourly")


def test_zero_duration_rejected():
    with pytest.raises(ValueError):
        make_task(duration=0)


def test_negative_duration_rejected():
    with pytest.raises(ValueError):
        make_task(duration=-15)


def test_empty_description_rejected():
    with pytest.raises(ValueError):
        Task(description="   ", due_at=BASE, duration_minutes=10)


def test_empty_owner_name_rejected():
    with pytest.raises(ValueError):
        Owner(name="")


def test_owner_with_no_pets_has_no_tasks():
    owner = Owner(name="Jordan")
    assert owner.get_all_tasks() == []
    sched = Scheduler(owner)
    assert sched.sort_by_due_time() == []
    assert sched.detect_conflicts() == []


def test_pet_with_no_tasks():
    owner = Owner(name="Jordan")
    owner.add_pet(Pet(name="Mochi", species="dog"))
    sched = Scheduler(owner)
    assert sched.get_all_tasks() == []
    assert sched.filter_tasks(pet_name="Mochi") == []
