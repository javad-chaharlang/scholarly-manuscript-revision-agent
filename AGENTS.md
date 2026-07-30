# Repository Instructions

## Purpose

This repository defines a scholarly manuscript revision system that assists a
senior researcher with source-grounded manuscript revision, reviewer-comment
analysis, revision tracking, quality assurance, and reviewer-response
preparation.

These instructions apply to the entire repository.

## Scientific integrity

- Ground every scientific revision in the source manuscript, verified
  references, supplied experimental records, journal instructions, or an
  explicit author decision.
- Never invent references, citations, results, experiments, methods, claims,
  page numbers, line numbers, section locations, or evidence.
- Do not infer that an experiment, analysis, check, or manuscript change was
  performed merely because it was proposed or drafted.
- Clearly distinguish draft language and unverified results from approved,
  verified, final content.
- Escalate missing evidence, ambiguous reviewer intent, and conflicts among
  manuscript sources to the author. Do not resolve them by speculation.

## Reviewer-comment identity and traceability

- Preserve reviewer comments exactly, except for documented correction of
  encoding artifacts.
- Give every reviewer comment a stable identifier in the form `R1-C01`,
  `R1-C02`, `R2-C01`, and so on.
- Use the revision workbook or project database as the single source of truth.
- Maintain traceability among, at minimum:
  - reviewer-comment identifier and exact comment;
  - interpretation;
  - required action;
  - manuscript change;
  - supporting evidence;
  - highlight color;
  - verification status; and
  - response-letter entry.
- Do not state that a change is complete until it has been applied to the
  manuscript and verified.

## Human approval gates

Obtain explicit human approval before:

- accepting or changing novelty claims;
- accepting experimental conclusions;
- accepting statistical interpretations;
- rejecting, declining, or only partially addressing a reviewer request; and
- releasing the final deliverables.

Treat an approval as scoped to the recorded proposal. Request approval again
when the scientific meaning, evidence, or planned response materially changes.

## Confidentiality and source control

- Keep unpublished manuscripts, reviewer files, experimental results,
  references containing confidential annotations, author information, and
  project workspaces outside Git.
- Commit only code, policies, templates, documentation, and anonymous synthetic
  fixtures.
- Never place secrets, credentials, or real manuscript data in configuration,
  examples, logs, tests, or generated artifacts.

## Document and release quality

- Apply the repository highlight policy exactly.
- Render every Word document and visually inspect all pages before final
  release. Check pagination, tracked or highlighted text, tables, figures,
  equations, captions, references, and cross-references.
- Require exact consistency across the manuscript, revision workbook, and
  response letter. A reviewer-comment status, described change, location,
  highlight, and evidence must agree in all three.
- Block final release while any required approval, integrity check, visual
  inspection, or cross-document consistency check is unresolved.
