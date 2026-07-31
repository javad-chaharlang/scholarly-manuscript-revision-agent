# Phase 6 deterministic scientific QA

Phase 6 audits immutable highlighted and clean DOCX outputs and local registries.
It performs no network access, OpenAI API calls, bibliographic lookup, manuscript
renumbering, scientific correction, or destructive equation parsing.

## Inputs and boundary

The project must contain outputs/Revision_Master.xlsx. Supply the highlighted
and clean manuscripts explicitly. Optional result and reference registries are
local JSON files. Source files are hashed before checks and are never saved.

The auditors separate structural or mathematical checks from scientific and
bibliographic verification. A percentage calculation can show that displayed
values disagree; it cannot establish which scientific value is correct.
DOI-like strings are checked structurally only and are never described as valid.

## Run the audit

    python scripts/run_scientific_qa.py \
      --project-root <private-project> \
      --highlighted-manuscript <highlighted.docx> \
      --clean-manuscript <clean.docx> \
      --results-registry <results.json> \
      --reference-registry <references.json> \
      --config templates/scientific_qa_config.yaml \
      --fail-on-blockers

Technical failures return exit code 1. With --fail-on-blockers, a successful
audit containing blockers returns exit code 2. Console output contains only
counts, readiness, and paths.

Outputs are audit/scientific_qa_report.json,
audit/scientific_qa_report.csv, outputs/Scientific_QA_Report.xlsx,
audit/qa_decision_template.json, and audit/final_release_blockers.json.
Revision_Master.xlsx receives QA findings and dashboard/specialized-sheet
updates without overwriting author notes or recorded decisions.

## Decisions and verification

Supported decisions are RESOLVE, ACCEPT_RISK, DEFER, NOT_APPLICABLE,
NEED_MORE_EVIDENCE, and MANUAL_CORRECTION_REQUIRED. RESOLVE requires a
resolution; ACCEPT_RISK requires justification; NEED_MORE_EVIDENCE requires an
evidence request. A blocker risk acceptance also requires an explicit decision
maker.

    python scripts/import_qa_decisions.py --project-root <project> --decision-file <json>
    python scripts/verify_qa_resolution.py --project-root <project>

Resolution verification rejects undocumented resolved items and unjustified
readiness. READY cannot be reported while unresolved blockers or critical
evidence-integrity issues remain. These checks do not replace rendered
page-by-page visual inspection or the final human release approval.
