# Response and Release Workflow

Phase 7 converts verified revision records into a response-to-reviewers package,
audits agreement among project artifacts, and creates an immutable submission
package only after every release gate passes. It is a local, deterministic
workflow. It does not call the OpenAI API and it does not draft scientific prose.

## Required state

Run Phase 7 only after revision execution and scientific QA. The project must
contain its manifest, exact reviewer-comment inventory, approved revision plan,
revision drafts, Change Log, clean and highlighted manuscripts, revision
workbook, QA report, and any applicable evidence and reference registries.
Original inputs remain unchanged and outside release packages.

The revision workbook and project JSON records are the traceability sources of
truth. A manuscript change is reportable only when an approved action maps to a
verified Change Log record and the applied text can be found in the highlighted
manuscript.

## 1. Prepare and complete response drafts

`prepare_response_drafts(project_root)` writes
`working/response_drafting_package.json`. Each entry contains the exact comment,
approved interpretation and actions, applied changes, verified evidence and
references, verified locations, and unresolved limitations. The
`author_response` field remains blank. Deterministic code never invents the
scientific response.

An author or authorized drafting process completes the structured JSON. Import
is strict: unknown or duplicated comments, changed comment text, unlogged
changes, missing evidence, missing references, and unapproved declines are
rejected.

```powershell
python scripts/generate_response_letter.py `
  --project-root <project-path> `
  --response-draft <completed-response.json>
```

This creates:

- `outputs/Response_to_Reviewers.docx`
- `working/response_package.json`
- `audit/response_generation_report.json`

The DOCX contains editable text, project metadata, an editor cover letter, a
major-revision summary, point-by-point bordered response blocks, general
revisions, and a closing statement. Reviewer 1 uses Yellow, Reviewer 2 uses
Bright Green, and editor/shared/general comments use Violet.

## 2. Verify the response

```powershell
python scripts/verify_response_letter.py `
  --project-root <project-path> `
  --response-letter <response-docx>
```

Verification checks comment identity, action and Change Log mappings, applied
manuscript text, highlights, evidence, references, locations, resolution states,
and the exact comment text in the DOCX. Failed entries become `BLOCKED`; only
entries satisfying every applicable check become `VERIFIED`.

Use stable structural locations such as `Section 2.3`, `Table 8`, `Figure 11`,
`Equation (14)`, `Paragraph PAR-0042`, or `Reference [29]`. Page and line
locations require explicitly extracted rendered-page metadata and a verified
text match. Word line numbers are never inferred.

## 3. Run the final consistency audit

```powershell
python scripts/run_final_consistency_check.py `
  --project-root <project-path>
```

This creates JSON and CSV consistency reports, the final-release checklist, and
the final-release report. It also synchronizes `Response_Map`, `Dashboard`, and
`QA_Findings` in `Revision_Master.xlsx` without overwriting author notes.

The audit compares reviewer comments, revision actions and drafts, author
decisions, Change Log records, clean and highlighted manuscripts, workbook,
scientific QA, response package and DOCX, and evidence/reference registries.
Every comment must end in one explicit state: fully addressed, partially
addressed, respectfully declined with justification, deferred with reason,
blocked by missing evidence, or not applicable with explanation.

## 4. Final-release gate

Readiness is one of `BLOCKED`, `NOT_READY`, `READY_WITH_WARNINGS`, or `READY`.
`READY` is impossible while a comment is missing, a response falsely reports a
change, empirical evidence is missing, a blocker remains, manuscript and
response values conflict, clean/highlighted text differs, or an unapproved
revision was applied.

The gate also requires successful file-open checks, structural QA, a recorded
visual inspection of every Word document, and explicit final human approval.
Approval is scoped to the evaluated artifacts and must be recorded again after
any material change. `READY_WITH_WARNINGS` can be packaged only with explicit
author approval.

## 5. Record manual visual-QA decisions

When automated Word-to-PDF rendering is unavailable, prepare the deterministic
decision template:

    python scripts/manual_visual_qa.py --project-root <project-path> --prepare

The author or designated reviewer must open and inspect all five named
artifacts, complete every field, and explicitly choose APPROVED or REJECTED for
each artifact. The template contains current SHA-256 hashes but contains no
inferred decisions. Import the completed record with:

    python scripts/manual_visual_qa.py --project-root <project-path> --decisions <completed-manual-visual-qa.json>

Import validates the exact artifact set, decision fields, timestamps, approval
criteria, and hashes before writing
audit/manual_visual_qa_decisions.json. It then reruns cross-document consistency
and final readiness. Missing, incomplete, stale, or rejected decisions retain
MANUAL_VISUAL_QA_REQUIRED; they never imply approval.

## 6. Build an immutable submission package

```powershell
python scripts/build_release_package.py `
  --project-root <project-path> `
  --release-name release_v001
```

The builder refuses a non-releasable project and refuses an existing release
name. Each release is stored under
`Submission_Package/release_vNNN/`. Only allowlisted artifacts are copied, and
the manifest records each released file's SHA-256 hash and size. Reviewer source
files, original manuscripts, experimental source files, secrets, databases,
internal prompts, temporary files, and synthetic fixtures are excluded.

After any correction, regenerate affected outputs, repeat response verification,
rerun scientific QA and consistency checks, repeat visual inspection, and obtain
new final approval before building a new immutable release version.
