# Scholarly Revision Studio user interface guide

> Screenshot placeholders and the real-project pilot are documented in
> `phase9-interface-overview.md`. Use `ui-quality-checklist.md` for manual
> light/dark, desktop/narrow, English/Persian, accessibility, and artifact QA.

Phase 9 provides a fully local Streamlit interface over the repository's
deterministic intake, gap-analysis, revision-execution, scientific-QA,
response, visual-QA, and release services. It does not call the OpenAI API and
does not perform network research.

## Start the application

Install the project and run:

    python -m pip install -e .
    python scripts/run_app.py

The launcher prints the local URL, normally http://localhost:8501, before
starting Streamlit. The server binds to localhost. Use --headless and --port
when a non-default local launch is required.

## Workspace and privacy boundary

Choose a workspace root outside this Git repository before opening or creating
a project. The application refuses an in-repository workspace. Each project
uses the existing private layout:

    <workspace>/<project-slug>/
      input/
      working/
      outputs/
      rendered/
      audit/
      config/

The workspace-level project registry is
<workspace>/.scholarly_revision/registry.json. It contains safe project
metadata and absolute local project paths, not reviewer or manuscript text.
Project state is stored in config/project_state.json; its read-only,
append-only timeline is audit/project_timeline.jsonl.

Uploaded sources are validated before project creation, copied into the
project, and never overwritten. Reviewer, manuscript, editor-letter, and
response-sample inputs must be DOCX. Result and reference registries must be
readable JSON. The application does not display secrets and does not put full
confidential text into logs.

## New Project wizard

The five-step wizard collects:

- project name, manuscript ID and title, journal, and revision round;
- reviewer count, manuscript and response languages, and citation style;
- result status and external workspace root;
- required reviewer and manuscript DOCX files; and
- optional editor-letter DOCX, result-registry JSON, reference-registry JSON,
  and response-sample DOCX.

Existing project directories are never replaced by the UI. Create a distinct
project name when a slug already exists.

Before creation, the confirmation step displays file sizes and SHA-256 hashes,
validates DOCX structure, rejects zero-byte or empty reviewer files, and
reiterates the external-workspace privacy boundary.

## Navigation and appearance

Grouped top navigation follows workflow order and is built explicitly with
`st.navigation` and `st.Page`. The shared shell shows selected project,
manuscript ID, workflow state, readiness, journal, round, decision maker,
abbreviated workspace, privacy status, last-save time, and a clickable
workflow stepper. Streamlit settings provide separate light and dark themes.
English is the default; Persian labels use RTL while manuscript content
direction remains independent.

## Project states and actions

The state machine is persisted and enforced by the orchestrator:

    NEW -> INTAKE_PENDING -> INTAKE_REVIEW
      -> GAP_ANALYSIS_PENDING -> PLAN_APPROVAL
      -> REVISION_DRAFTING -> TEXT_APPROVAL
      -> REVISION_APPLICATION -> SCIENTIFIC_QA
      -> RESPONSE_PREPARATION -> VISUAL_QA
      -> READY_FOR_RELEASE -> RELEASED

Intake may go directly to GAP_ANALYSIS_PENDING when no manual review or warning
exists. Any active phase may enter BLOCKED; it can resume only the recorded
prior state. Buttons for actions not valid in the current state are disabled,
and the service rejects invalid direct calls as well.

The Dashboard shows project state, counts by reviewer, manual-review count,
revision and approval counts, draft texts awaiting approval, QA blockers,
verified responses, release readiness, blockers, the recommended next action,
and the read-only audit timeline.

## Page workflow

1. **Dashboard** provides safe summary metrics and timeline events.
2. **New Project** validates inputs and creates a private project.
3. **Input Files** shows names, sizes, SHA-256 hashes, and versions.
4. **Reviewer Comments** shows immutable exact comments and confirms intake
   review when required.
5. **Gap Analysis** prepares a blank local package and strictly imports the
   completed JSON.
6. **Revision Plan** records APPROVE, APPROVE_WITH_MODIFICATION,
   REJECT_WITH_JUSTIFICATION, NEED_MORE_EVIDENCE, or DEFER.
7. **Text Approval** records APPROVE_TEXT, APPROVE_TEXT_WITH_MODIFICATION,
   REJECT_TEXT, REQUEST_REWRITE, NEED_MORE_EVIDENCE, or DEFER_TEXT.
8. **Manuscript Versions** prepares/imports draft text, creates versioned
   manuscript copies, verifies them, and shows hashes and version numbers.
9. **Reference Audit** shows read-only structural citation/reference findings.
10. **Scientific QA** runs local audits and imports explicit QA decisions.
11. **Response Letter** prepares/imports response records and verifies the
    generated DOCX against the source of truth.
12. **Visual QA** requires a manual decision and all inspection fields for
    every mandatory artifact. No visual approval is inferred.
13. **Final Release** shows every mandatory check and requires the exact
    confirmation RELEASE <project-id> before creating an immutable package.
14. **Settings** records the local decision-maker label and displays the fixed
    highlight policy and registry location.

Tables that contain governed records are read-only. Author-editable content is
limited to explicit forms or downloaded structured templates that are
strictly validated on import.

## Approval and release safeguards

Every plan and text decision is preserved in the governed project artifacts
and summarized in the audit timeline without confidential prose. A decision is
never inferred from a blank field, generated file, or completed automated
check.

The fixed highlight policy is:

- Reviewer 1: Yellow;
- Reviewer 2: Bright Green; and
- shared/general: Violet.

Verified manuscript copies and a verified response letter receive download
buttons. Final package artifacts become downloadable after release. Final
release remains refused while any required approval, unresolved blocker,
scientific-integrity check, response verification, cross-document consistency
check, file-open check, current artifact hash, or explicit visual inspection
is missing or failed.

If an artifact changes after visual approval, its hash no longer matches and
the approval is stale. Repeat the affected deterministic checks, visual
inspection, and final approval before creating a new release version.
