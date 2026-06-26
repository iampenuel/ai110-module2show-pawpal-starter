# PawPal+ Project Reflection

## 1. System Design

**a. Initial design**

The initial UML (see [diagrams/uml_draft.mmd](diagrams/uml_draft.mmd)) centered
on four classes with a clear containment hierarchy:

- **Owner** contains **Pets** (`Owner.pets`).
- **Pet** contains **Tasks** (`Pet.tasks`).
- **Scheduler** holds a reference to the **Owner** and manages tasks across
  *all* of that owner's pets, rather than operating on a single pet.
- **Task** is the unit of work, with a due time, duration, priority, and
  recurrence.

The three user actions the design had to support were: **add pets**,
**schedule care tasks**, and **view an organized daily plan** (sorted,
filtered, conflict-checked).

**b. Design changes**

The design changed in three concrete ways during implementation:

1. **Conflict detection moved from exact-time matching to duration-based
   overlap.** The first sketch compared `due_at` values; in code this misses
   real conflicts (a 30-minute walk overlapping a 10-minute medication that
   starts 20 minutes later). I added `Task.end_time()` and `Task.overlaps()`
   and changed `Scheduler.detect_conflicts()` to compare half-open
   `[due_at, end_time)` ranges, which also correctly treats back-to-back tasks
   as *non*-conflicting.
2. **Recurrence coordination moved into the Scheduler.** Originally `Task` was
   going to handle its own recurrence on completion. That made it hard to know
   *which pet* to attach the next occurrence to. I split it: `Task` knows how to
   build its next occurrence (`create_next_occurrence()`), but
   `Scheduler.complete_task()` coordinates marking complete and attaching the
   new task to the correct pet, and makes the operation idempotent.
3. **Added stable `task_id`s for persistence.** The draft had no identifier;
   JSON round-tripping and "complete this specific task" needed a stable key, so
   each `Task` gained an auto-generated `task_id`.

The final design is recorded in [diagrams/uml_final.mmd](diagrams/uml_final.mmd)
and matches the shipped code.

---

## 2. Scheduling Logic and Tradeoffs

**a. Constraints and priorities**

The scheduler reasons about: **due time**, **duration** (which together define a
task's time range), **priority** (high/medium/low), **completion status**,
**pet** ownership, **recurrence** (once/daily/weekly), and **overlap
conflicts**. Time and duration mattered most because they define whether two
tasks physically collide; priority matters next because when the day is full,
the owner needs to know what to protect first.

**b. Tradeoffs**

Two deliberate tradeoffs:

- **The scheduler detects calendar conflicts but does not estimate travel time**
  between appointments. Two tasks that merely touch end-to-start are treated as
  fine even though a real owner might need transition time. This keeps the
  overlap rule simple and predictable.
- **`find_next_available_slot` uses fixed 15-minute increments.** This makes the
  search fast and the results predictable/round, at the cost of not finding a
  hypothetical "fits exactly in this 7-minute gap" slot. For day-to-day pet care
  planning, 15-minute granularity is more than precise enough.

---

## 3. AI Collaboration

**a. How you used AI**

I split the work across two tools. **ChatGPT** was used for rubric-first
planning: turning the grading rubric into a checklist that mapped every
requirement to specific files, methods, tests, evidence artifacts, and commits.
**Claude Code** was used for repository-aware execution: inspecting the actual
starter files, implementing `pawpal_system.py` / `main.py` / `app.py` / the test
suite, running everything, and reviewing diffs before each commit. The most
helpful prompts were ones that named explicit constraints ("standard library
only", "don't mutate the pets' task lists", "make completion idempotent").

**b. Judgment and verification**

One suggestion I **modified**: the initial Streamlit implementation pulled in
`pandas` just to render tables. That added an unnecessary dependency for what is
fundamentally a list of dictionaries, so I removed `pandas` and rendered the
same data by passing plain lists of dicts to `st.dataframe`, keeping
`requirements.txt` limited to `streamlit` and `pytest`.

One suggestion I **accepted**: representing scheduler query results as a small
`ScheduleEntry(pet, task)` record instead of bare `Task` objects. Because the
scheduler merges tasks from multiple pets, keeping the owning pet attached to
each task made every downstream display (CLI tables, Streamlit tables, conflict
messages) straightforward.

I verified AI output by running `pytest -v` (44 passing tests), running
`python main.py` and reading the real output, booting the Streamlit app in
headless mode (HTTP 200 health check, no tracebacks), and reading `git diff`
before each commit.

---

## 4. Testing and Verification

**a. What you tested**

I tested core class behavior, all required algorithms (chronological sort,
multi-pet filtering, exact/partial/adjacent conflict detection), recurrence
(daily +1 day, weekly +7 days, once-does-not-recur, idempotent completion), the
stretch algorithms (priority-first sort, next-available-slot in
open/occupied/full windows), JSON round-tripping, and validation/edge cases
(invalid priority/frequency, non-positive duration, empty names, owner with no
pets, missing/malformed/wrong-shaped save files). The conflict and recurrence
tests were the most important because they encode the rules most likely to be
implemented subtly wrong.

**b. Confidence**

Confidence is **4/5**. The 44 deterministic tests all pass and the CLI output is
real. Remaining gaps: UI behavior is checked by a headless boot rather than an
automated browser test, and the scheduler does not yet model multi-day
calendars or travel time. With more time I would add property-based tests for
conflict detection and a browser-driven Streamlit test.

---

## 5. Reflection

**a. What went well**

The clean separation between the engine (`pawpal_system.py`) and the two front
ends. Because no scheduling logic lives in `app.py` or `main.py`, the same code
is tested once and reused everywhere, and the test suite gives real confidence.

**b. What you would improve**

I would make the next-available-slot search span multiple days and respect a
configurable working-hours window, and add recurrence end-dates so daily tasks
don't recur forever.

**c. Key takeaway**

The most important lesson was treating AI-generated code as a **proposal**, not
an answer. As the lead architect I made the structural decisions (containment
hierarchy, where recurrence is coordinated, what the scheduler returns), and I
verified every claim with tests, real CLI runs, a Streamlit smoke test, and diff
review before committing. The `pandas` removal is a concrete example of
overriding a convenient-but-unnecessary AI suggestion to keep the design lean.
