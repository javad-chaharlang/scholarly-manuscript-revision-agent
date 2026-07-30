# Architecture

## Phase 1 scope

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

## Future runtime option

The initial workflow uses Codex directly for reasoning and orchestration. A
future implementation may optionally migrate orchestration to the OpenAI
Agents SDK when multi-agent handoffs, persisted runs, formal tool contracts, or
production observability justify that complexity. Such a migration is not
required for Phase 1 and must preserve the same integrity rules, approval
gates, deterministic processing boundary, and local confidentiality model.
