# Scholarly Revision Studio interface overview

Phase 9 is a local Streamlit workspace over the repository's deterministic
services. It uses grouped top navigation, a persistent project selector, a
project context shell, and a state-aware workflow stepper. UI pages do not
perform scientific interpretation or duplicate approval/release logic.

## Navigation

The exact order is Dashboard, Projects, New Project, Input Files, Reviewer
Comments, Gap Analysis, Revision Plan, Text Approval, Manuscript Versions,
Reference Audit, Scientific QA, Response Letter, Visual QA, Final Release,
Audit Timeline, and Settings. Future workflow pages are omitted until their
state becomes reachable; their service actions remain guarded as well.

## Starting and recovering

Install with `python -m pip install -e .` and start with
`python scripts/run_app.py`. Select a workspace outside Git. The workspace
registry and each project's persisted state allow the project to resume after
the app restarts; Session State is used only for UI convenience.

## Real-project pilot

1. Create an empty external confidential workspace.
2. Use a non-sensitive dry run to verify local storage and Word rendering.
3. Create the real project through the five-step wizard.
4. Confirm the input hashes and exact reviewer-comment inventory.
5. Complete each analysis/import and explicit approval gate in workflow order.
6. Render and inspect every Word deliverable.
7. Reconcile manuscript, workbook, response letter, QA report, and hashes.
8. Record explicit visual decisions and final release approval.
9. Build a new immutable release name; never overwrite a prior release.

## Screenshot placeholders

- `[Screenshot: dashboard in light theme]`
- `[Screenshot: project portfolio and workflow shell]`
- `[Screenshot: five-step intake wizard]`
- `[Screenshot: reviewer comment master-detail view]`
- `[Screenshot: plan and exact-text approval gates]`
- `[Screenshot: scientific and visual QA dashboards]`
- `[Screenshot: blocked and ready final-release states]`
- `[Screenshot: Persian RTL navigation]`

## Troubleshooting and upgrades

Unreadable uploads, invalid paths, stale hashes, incomplete decisions, and
state-invalid actions are shown as redacted local errors. Correct the source
record instead of bypassing the gate. Before upgrading, back up the external
workspace, install the new package, run the full test suite, open a synthetic
project, and confirm state resume and artifact hashes before opening real data.
