# Real-project Pilot Mode

Pilot Mode is enabled by default for newly created projects. It is intended
for the first real manuscripts while the author confirms context boundaries,
Word-object handling, and cross-document consistency.

## Restrictions

Pilot Mode disables automatic batch execution, permits at most one reviewer
comment or one small group per task, requires transmission approval for every
semantic run, requires import approval for every validated output, and creates
an extra pre-run backup of the task, approved context, and prompt. Complex
Word objects remain manual. Final release is blocked until all pilot checks
have an explicit named approval record.

## First real article

1. Create the project in an external confidential workspace and confirm
   copied-file hashes.
2. Review extracted comment boundaries and preserve exact reviewer wording.
3. Start with one comment. Prepare context, inspect every included excerpt and
   exclusion, then approve transmission only if the package is minimal.
4. Run Codex and inspect raw output, validation findings, and the normalized
   output. Approve import only when the semantic content is acceptable.
5. Repeat for gap analysis and plan drafting. Keep Gate 1 decisions explicit.
6. Draft text only for approved actions. Keep evidence requirements visible
   and decide every exact text at Gate 2.
7. Apply approved text with deterministic tools. Confirm that input hashes are
   unchanged and inspect highlighted and clean versions.
8. Run deterministic scientific QA. Treat semantic QA as optional additional
   findings.
9. Draft responses only from verified project records. Verify each described
   change and location.
10. Render every Word artifact and record manual page decisions, including
    tables, figures, equations, captions, references, and cross-references.
11. In Agent Tasks, review the real-project checklist and explicitly approve
    all Pilot Mode checks. The normal final-release confirmation is still
    required.

## Restart and recovery drill

After at least one completed task, stop and restart Streamlit. Confirm that the
task, run, raw output, validation result, and author decision remain visible.
If a worker was interrupted, its run becomes `RECOVERY_REQUIRED` and its task
becomes `BLOCKED`. Inspect its audit directory, then cancel or create an
explicit retry. Never manually relabel an interrupted run as complete.

Pilot approval covers only the recorded project artifacts. Repeat affected
checks if context, manuscript outputs, response records, rendered pages, or
source hashes change.
