# Scholarly Manuscript Revision Agent

An agentic research workflow for revising scholarly manuscripts and preparing complete responses to editors and reviewers.

## Core capabilities

- Reviewer-comment extraction and classification
- Comment-to-revision traceability
- Structured revision planning
- Scientific manuscript revision
- Reference and citation auditing
- Experimental-result integrity checks
- DOCX formatting and highlighting
- Figure, table, equation, and cross-reference auditing
- Revision workbook generation
- Response-to-reviewers generation
- Final manuscript quality assurance

## Highlight policy

- Reviewer 1: Yellow
- Reviewer 2: Bright Green
- Shared and general revisions: Violet

## Planned outputs

1. Revised manuscript with highlights
2. Clean revised manuscript
3. Revision tracking workbook
4. Response-to-reviewers letter
5. Final quality-assurance report
6. Machine-readable audit log

## Privacy

Unpublished manuscripts, reviewer files, experimental results, API keys, author information, and project workspaces must not be committed to this repository.

## Scholarly Revision Studio

Phase 9 provides a production-oriented local Streamlit workspace with grouped
top navigation, a persisted project portfolio, a five-step intake wizard,
state-aware workflow dashboards, explicit approval gates, bilingual
English/Persian infrastructure, visual QA, and immutable release controls.

Start it with:

    python -m pip install -e .
    python scripts/run_app.py

Use only a confidential workspace outside this Git repository. See
`docs/user-interface-guide.md`, `docs/phase9-interface-overview.md`, and
`docs/ui-quality-checklist.md`.

## Development status

Version 0.3.0 — deterministic workflow through the Phase 9 interface
