"""PawPal+ Streamlit interface.

A thin presentation layer over ``pawpal_system.py``. All scheduling logic
lives in the engine module; this file only collects input, calls engine
methods, and renders the results. The active :class:`Owner` is preserved
across Streamlit reruns in ``st.session_state``.
"""

from __future__ import annotations

import io
import json
from datetime import datetime, time

import streamlit as st

from pawpal_system import (
    DEFAULT_SLOT_INCREMENT_MINUTES,
    VALID_FREQUENCIES,
    VALID_PRIORITIES,
    Owner,
    Pet,
    Scheduler,
    Task,
)

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="wide")

PRIORITY_ICON = {"high": "🔴", "medium": "🟡", "low": "🟢"}


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
def get_owner() -> Owner:
    """Return the owner stored in session state, creating a default one."""
    if "owner" not in st.session_state:
        st.session_state.owner = Owner(name="Jordan Rivera", contact="jordan@example.com")
    return st.session_state.owner


def scheduler() -> Scheduler:
    """Build a Scheduler over the current session owner."""
    return Scheduler(get_owner())


def entries_to_rows(entries) -> list[dict]:
    """Convert ScheduleEntry objects into display rows (list of dicts)."""
    return [
        {
            "Pet": e.pet.name,
            "Task": e.task.description,
            "When": e.task.due_at.strftime("%Y-%m-%d %H:%M"),
            "Dur (min)": e.task.duration_minutes,
            "Priority": f"{PRIORITY_ICON[e.task.priority]} {e.task.priority}",
            "Frequency": e.task.frequency,
            "Status": "✅ done" if e.task.completed else "⬜ open",
        }
        for e in entries
    ]


owner = get_owner()

st.title("🐾 PawPal+")
st.caption("Plan and organize care tasks across all of your pets.")

# ---------------------------------------------------------------------------
# Sidebar: owner, pets, persistence, reset
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("👤 Owner")
    with st.form("owner_form"):
        new_name = st.text_input("Owner name", value=owner.name)
        new_contact = st.text_input("Contact", value=owner.contact)
        if st.form_submit_button("Save owner"):
            if new_name.strip():
                owner.name = new_name.strip()
                owner.contact = new_contact.strip()
                st.success(f"Owner updated: {owner.name}")
            else:
                st.error("Owner name cannot be empty.")

    st.divider()
    st.header("🐕 Add a pet")
    with st.form("pet_form", clear_on_submit=True):
        pet_name = st.text_input("Pet name")
        pet_species = st.selectbox("Species", ["dog", "cat", "bird", "other"])
        pet_age = st.number_input("Age (years)", min_value=0, max_value=40, value=1)
        pet_notes = st.text_input("Care notes", value="")
        if st.form_submit_button("Add pet"):
            if not pet_name.strip():
                st.error("Pet name cannot be empty.")
            else:
                try:
                    owner.get_pet(pet_name)
                    st.warning(f"A pet named {pet_name} already exists.")
                except KeyError:
                    owner.add_pet(
                        Pet(name=pet_name, species=pet_species, age=int(pet_age), notes=pet_notes)
                    )
                    st.success(f"Added {pet_name.strip()} 🐾")

    st.divider()
    st.header("💾 Persistence")
    st.download_button(
        "Download owner JSON",
        data=json.dumps(owner.to_dict(), indent=2),
        file_name="pawpal_owner.json",
        mime="application/json",
        help="Save the current owner, pets, and tasks to a JSON file.",
    )
    uploaded = st.file_uploader("Load owner JSON", type="json")
    if uploaded is not None and st.button("Load from file"):
        try:
            data = json.load(io.TextIOWrapper(uploaded, encoding="utf-8"))
            st.session_state.owner = Owner.from_dict(data)
            st.success("Loaded owner from file.")
            st.rerun()
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            st.error(f"Could not load file: {exc}")

    st.divider()
    st.header("♻️ Reset")
    confirm_reset = st.checkbox("I understand this clears all session data")
    if st.button("Reset demo data", disabled=not confirm_reset):
        st.session_state.pop("owner", None)
        st.success("Session reset.")
        st.rerun()


# ---------------------------------------------------------------------------
# Main body
# ---------------------------------------------------------------------------
if not owner.pets:
    st.info("👈 Add at least one pet in the sidebar to start scheduling tasks.")
    st.stop()

tab_schedule, tab_tasks, tab_smart = st.tabs(
    ["➕ Add Task", "📋 All Tasks", "🧠 Smart Scheduling"]
)

# --- Add task tab ----------------------------------------------------------
with tab_schedule:
    st.subheader("Schedule a care task")
    with st.form("task_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            sel_pet = st.selectbox("Pet", [p.name for p in owner.pets])
            description = st.text_input("Task description", value="Walk")
            duration = st.number_input("Duration (minutes)", min_value=1, max_value=480, value=30)
        with col2:
            due_date = st.date_input("Date")
            due_time = st.time_input("Time", value=time(8, 0))
            priority = st.selectbox("Priority", list(VALID_PRIORITIES), index=1)
            frequency = st.selectbox("Frequency", list(VALID_FREQUENCIES))
        if st.form_submit_button("Add task"):
            try:
                due_at = datetime.combine(due_date, due_time)
                task = Task(
                    description=description,
                    due_at=due_at,
                    duration_minutes=int(duration),
                    priority=priority,
                    frequency=frequency,
                )
                owner.get_pet(sel_pet).add_task(task)
                st.success(f"Added '{task.description}' for {sel_pet}.")
            except (ValueError, KeyError) as exc:
                st.error(str(exc))

# --- All tasks tab ---------------------------------------------------------
with tab_tasks:
    st.subheader("All tasks across pets")
    sched = scheduler()

    fcol1, fcol2, fcol3 = st.columns(3)
    with fcol1:
        f_pet = st.selectbox("Filter by pet", ["All"] + [p.name for p in owner.pets])
    with fcol2:
        f_priority = st.selectbox("Filter by priority", ["All"] + list(VALID_PRIORITIES))
    with fcol3:
        f_status = st.selectbox("Filter by status", ["All", "open", "done"])

    completed = {"All": None, "open": False, "done": True}[f_status]
    entries = sched.filter_tasks(
        pet_name=None if f_pet == "All" else f_pet,
        priority=None if f_priority == "All" else f_priority,
        completed=completed,
    )

    if entries:
        st.dataframe(
            entries_to_rows(entries),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No tasks match the current filters.")

    st.markdown("#### Complete a task")
    open_entries = [e for e in sched.get_all_tasks() if not e.task.completed]
    if open_entries:
        labels = {
            f"{e.pet.name} — {e.task.description} @ {e.task.due_at.strftime('%m-%d %H:%M')}": e.task.task_id
            for e in open_entries
        }
        choice = st.selectbox("Open task", list(labels.keys()))
        if st.button("Mark complete"):
            spawned = sched.complete_task(labels[choice])
            if spawned is not None:
                st.success(
                    f"Completed. Next occurrence created for "
                    f"{spawned.due_at.strftime('%a %m-%d %H:%M')}."
                )
            else:
                st.success("Task completed.")
            st.rerun()
    else:
        st.info("No open tasks to complete.")

# --- Smart scheduling tab --------------------------------------------------
with tab_smart:
    sched = scheduler()

    st.subheader("⏱ Chronological plan")
    chrono = sched.sort_by_due_time()
    if chrono:
        st.dataframe(
            entries_to_rows(chrono),
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("🥇 Priority-first plan")
    prio = sched.sort_by_priority_and_time()
    if prio:
        st.dataframe(
            entries_to_rows(prio),
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("⚠️ Conflicts")
    conflicts = sched.detect_conflicts()
    if conflicts:
        for c in conflicts:
            st.warning(c.describe())
    else:
        st.success("No scheduling conflicts detected.")

    st.subheader("📅 Find next available slot")
    scol1, scol2, scol3 = st.columns(3)
    with scol1:
        slot_dur = st.number_input("Needed duration (min)", min_value=5, max_value=240, value=30)
    with scol2:
        s_date = st.date_input("Search date", key="slot_date")
    with scol3:
        st.caption(f"Search window 06:00–22:00, in {DEFAULT_SLOT_INCREMENT_MINUTES}-min steps.")
    if st.button("Find slot"):
        start = datetime.combine(s_date, time(6, 0))
        end = datetime.combine(s_date, time(22, 0))
        slot = sched.find_next_available_slot(int(slot_dur), start, end)
        if slot is not None:
            st.success(f"Earliest free slot: {slot.strftime('%A %Y-%m-%d %H:%M')}")
        else:
            st.error("No free slot of that length in the search window.")
