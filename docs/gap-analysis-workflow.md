# Phase 4 gap-analysis and approval workflow

Phase 4 is local and deterministic. It reads manuscript structure, packages
source context for semantic assessment, validates a completed assessment,
generates an unapproved plan, updates the revision workbook, and records
explicit author decisions. It does not call an API, use OCR, search the
network, rewrite the manuscript, or claim that a plan was applied.

## Inputs and confidentiality

Run Phase 3 first. The private project root must contain the project manifest,
working/reviewer_comments.json, and outputs/Revision_Master.xlsx. Keep the
project outside Git. The manuscript reader opens the supplied DOCX read-only
and never saves it.

## Structural intake

    python scripts/prepare_gap_analysis.py --project-root <project> --manuscript-file <docx>

The command writes manuscript_structure.json, gap_analysis_input.json, and
gap_analysis_template.json under working. The reader preserves body and table
order, assigns stable paragraph and object IDs, records explicit heading
levels, captions, citation-like numeric patterns, detectable highlights, and
the reference boundary.

Element page_number values remain null because DOCX does not provide stable
paragraph pagination. An optional top-level page count is copied only from
DOCX application metadata and is never treated as a verified location.
Heuristic heading/equation candidates and uncaptioned tables are marked
uncertain with a reason and require manual review.

## Completing the analysis

Preparation leaves every semantic assessment blank. Codex or the author may
complete the project copy using manuscript evidence, verified records, or an
explicit author decision. Preserve each comment_id and original_comment
exactly.

Allowed coverage values are FULLY_ADDRESSED, PARTIALLY_ADDRESSED,
NOT_ADDRESSED, NOT_APPLICABLE, and CANNOT_DETERMINE.

Use action_proposals for multiple actions or shared actions. Proposals with a
common shared_action_key are reconciled and linked to all affected comments.
Shared actions receive VIOLET. Missing evidence remains explicit.

## Strict import and plan generation

    python scripts/import_gap_analysis.py --project-root <project> --analysis-file <json>

Import rejects unknown, missing, duplicate, or text-altered comments;
unsupported coverage values; evidence-free FULLY_ADDRESSED or VERIFIED
claims; completed-experiment claims without evidence IDs; and absolute page or
line locations that were not explicitly verified. It preserves author fields
and records an import timestamp and SHA-256 source hash.

The command writes gap_analysis_imported.json and revision_plan.json under
working, gap_analysis_report.json under audit, and Phase 4 fields into
Revision_Master.xlsx. Every action begins PLANNED and PENDING. No applied
location, verification, manuscript modification, or approval is inferred. An
existing approved plan is never overwritten.

## Explicit author approval gate

List actions or export a decision template:

    python scripts/review_revision_plan.py --project-root <project> --list
    python scripts/review_revision_plan.py --project-root <project> --export-template <json>

Record one scoped decision:

    python scripts/review_revision_plan.py --project-root <project> --action-id ACT-0001 --decision APPROVE --decision-maker <name>

REJECT_WITH_JUSTIFICATION requires an author note.
APPROVE_WITH_MODIFICATION requires modified action text.
NEED_MORE_EVIDENCE requires an evidence request.
DEFER leaves the action pending and gives it DEFERRED action status.

The visible gate status is NOT_READY, READY_FOR_REVIEW, PARTIALLY_APPROVED,
APPROVED, or BLOCKED. A gate is never approved merely because a plan or
template exists. Substantive editing remains blocked until the applicable
explicit author approvals are recorded.
