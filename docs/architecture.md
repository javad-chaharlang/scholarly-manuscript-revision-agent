# Architecture

## Phase 10 application architecture

The application entry point is `scholarly_revision.ui.studio_app`. It builds
all pages explicitly with `st.navigation` and `st.Page`; file names do not
control navigation order. The reusable design layer contains tokens, theme,
layout, navigation, Material icons, translations, and native Streamlit
components. Custom static CSS is isolated in `ui/theme.py`.

Pages are intentionally thin. They load safe derived metadata and invoke the
unified orchestrator for state-changing work. The orchestrator and persisted
state machine remain authoritative for action availability, approvals,
immutable versions, QA blockers, response verification, and release.
Confidential project content remains in an external local workspace.

The optional semantic lane is split into four boundaries: AgentTaskService
governs task and human-gate transitions; AgentContextService builds and
redacts the exact author-reviewable payload; AgentWorkerService runs a
separate process around CodexBridgeService; and
AgentOutputValidationService validates every response before author review.
AgentRunRegistry persists atomic task, context, run, and audit records on disk.
Streamlit polls only safe metadata and therefore does not own task truth.

Codex CLI capabilities are detected from the installed executable and
`codex exec --help`. The bridge uses direct subprocess arguments, stdin,
explicit cwd, read-only sandboxing when available, bounded timeout, separated
stdout and stderr, cancellation, and no shell. The currently authenticated
CLI session is used; there is no direct API client or API-key requirement.

## Historical Phase 1 scope

Phase 1 establishes policy, workflow, configuration, and skill guidance. It
does not implement application logic, external API integration, or manuscript
processing.

## Runtime model

Codex is the reasoning and orchestration runtime. It interprets reviewer
intent, identifies gaps, proposes evidence-grounded revisions, manages approval
gates, coordinates workflow phases, and checks that the recorded rationale is
coherent.

Python tools are planned as deterministic file processors. They will parse and
write DOCX, PDF, spreadsheet, and structured records; apply exact highlights;
check identifiers, references, numbering, and cross-references; compare files;
and render artifacts for inspection. Deterministic tools perform the file
operation, while Codex reasons about what approved operation is needed.

This separation prevents a drafted instruction from being mistaken for an
applied and verified file change.

## Trust and storage boundaries

GitHub is source control for:

- source code;
- policies and skill instructions;
- safe configuration defaults;
- document templates; and
- anonymous synthetic fixtures.

A local workspace outside Git stores:

- unpublished manuscripts;
- editor and reviewer files;
- experimental records and results;
- author information and correspondence;
- confidential reference libraries; and
- generated revision deliverables.

Secrets and confidential research content must never enter Git history,
repository examples, logs, or fixtures.

## Source of truth and data flow

The revision workbook or a future local project database is the single source
of truth. Each reviewer comment receives a stable identifier and a linked
record of interpretation, planned action, evidence, manuscript change,
location, highlight, status, verification, approval, and response-letter text.

The planned flow is:

1. Confidential local inputs enter the intake process.
2. Codex inventories comments and develops a traceable revision plan.
3. The author approves scientifically consequential decisions.
4. Deterministic Python tools apply approved file changes.
5. Codex and deterministic checks verify integrity and consistency.
6. Word artifacts are rendered and visually inspected.
7. The author approves the final local release package.

The manuscript, source of truth, and response letter must agree exactly before
release.

## Approval and release boundary

Human approval is mandatory for the revision plan, novelty claims,
experimental conclusions, statistical interpretations, rejected or partially
addressed reviewer requests, and final release. Automated checks cannot replace
these decisions.

Word deliverables must be rendered and inspected page by page. Final release
remains blocked while evidence, approvals, formatting checks, or
cross-document reconciliation are unresolved.

## Planned outputs

The workflow will produce:

1. Highlighted revised DOCX.
2. Clean revised DOCX.
3. Revision workbook.
4. Response-to-reviewers letter.
5. Final quality-assurance report.
6. Machine-readable audit log.

All outputs remain in the confidential local workspace unless an explicitly
approved, anonymized artifact is intended for source control.

## Semantic runtime boundary

Codex proposes schema-constrained semantic records only. It never edits the
original manuscript or marks a scientific action approved, applied, verified,
or released. Deterministic workflows remain responsible for Word mutation,
hash verification, QA, rendering, and packaging. Gate 1, Gate 2, transmission,
import, Pilot Mode, visual-QA, and final-release decisions require explicit
named human records.
