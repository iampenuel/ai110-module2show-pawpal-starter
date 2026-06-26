# AI Interactions Log

This file documents how AI tools were used to build PawPal+, supporting the
agent-workflow and prompt-comparison stretch features.

---

## Agent Workflow (SF7)

**What task did you give the agent?**

Complete PawPal+ from its starter state: design the OOP system (UML), implement
the `Task` / `Pet` / `Owner` / `Scheduler` engine plus JSON persistence, build a
CLI demo and a Streamlit UI on top of it, write a thorough pytest suite, and
produce accurate documentation — working inside the existing repository,
verifying every claim, and committing in meaningful stages.

**What did the agent do?**

*Files created/modified:*

- `pawpal_system.py` — engine: `Task`, `Pet`, `Owner`, `Scheduler`,
  `ScheduleEntry`, `Conflict`, and `save_to_json` / `load_from_json`.
- `main.py` — CLI demo with a standard-library table formatter.
- `app.py` — replaced the placeholder Streamlit app with a functional,
  session-state-backed UI.
- `tests/test_pawpal.py` — 44-case pytest suite.
- `diagrams/uml_draft.mmd`, `diagrams/uml_final.mmd`, `diagrams/uml.mmd`.
- `README.md`, `reflection.md`, `ai_interactions.md`, `demo_output.txt`,
  `test_results.txt`.
- Removed a stale, accidentally-tracked `__pycache__/*.pyc` from version control.

*Commands the agent ran (representative):*

- Inspection: `git remote -v`, `git status --short`, `git log --oneline`,
  `find . -maxdepth 3 -type f`.
- Verification: `python -m py_compile ...`, `python -m compileall ...`,
  `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -v`,
  `python main.py | tee demo_output.txt`,
  `python -m streamlit run app.py --server.headless true` (HTTP 200 health
  check).
- Git: staged related files and committed in stages (skeleton → engine+CLI →
  Streamlit → tests → docs).

*Features completed:* chronological sorting, multi-pet filtering,
duration-based conflict detection, daily/weekly recurrence with idempotent
completion, priority-first sorting, next-available-slot search (the advanced
algorithmic capability), and JSON persistence.

**What did you have to verify or fix manually?**

- The agent's first Streamlit draft imported `pandas` only to render tables.
  This was an unnecessary dependency, so it was removed and the tables were
  rendered from plain lists of dicts — keeping `requirements.txt` to `streamlit`
  + `pytest`.
- A README draft initially summarized the pytest output with a `....` dots line
  that `pytest -v` never actually prints. It was corrected to show genuine,
  verbatim `PASSED` lines from the captured `test_results.txt`.
- The next-available-slot search increment (15 minutes) and the half-open
  overlap rule were checked by hand against the demo data before trusting them.

### Advanced algorithmic capability — `find_next_available_slot`

`Scheduler.find_next_available_slot(duration_minutes, search_start, search_end,
increment_minutes=15)` scans candidate start times from `search_start` toward
`search_end` in 15-minute steps and returns the first start whose
`[start, start + duration)` range overlaps **no incomplete task across any
pet**, or `None` when the window is full. Completed tasks are ignored. It is
covered by four tests (open window, occupied windows, full window → `None`,
completed tasks don't block), and demonstrated in section 8 of `main.py` output.

---

## Prompt Comparison (SF11)

| | Option A | Option B |
|-|----------|----------|
| **Model / tool used** | ChatGPT | Claude Code |
| **Prompt / strategy** | Rubric-first planning prompt mapping every grading requirement to files, methods, tests, evidence, commits, and safety constraints | Repository-aware agent execution: inspect the real files, implement code, run tests, review diffs |
| **Response summary** | A completeness checklist and scope plan | Working implementation plus feedback from the real codebase |
| **What was useful** | Clear coverage of every rubric point and good scope control | Direct, verifiable implementation grounded in the actual repo state |
| **Problems noticed** | A planning model doesn't know the final repo state and can propose more scope than needed (e.g. extra UML files) | An agent can over-engineer (e.g. reaching for `pandas`) unless boundaries and verification commands are explicit |
| **Decision** | Use as the architecture/plan | Use for implementation + verification |

**Which approach did you use in your final implementation and why?**

Both, in their strengths: ChatGPT's rubric-first plan defined *what* to build
and how it would be graded; Claude Code did the repository-aware
implementation, ran the tests and CLI, and surfaced the real codebase feedback.
Human verification tied them together — every AI proposal was checked against
passing tests, real CLI output, a Streamlit smoke test, and `git diff` review
before being committed. The one concrete course-correction during this run was
removing the agent's unnecessary `pandas` dependency, which is exactly the
"agent over-engineers unless bounded" risk noted above.
