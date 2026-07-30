---
name: manuscript-revision
description: Analyze and inventory reviewer comments, plan and perform source-grounded scholarly manuscript revisions, maintain revision traceability, audit references and scientific integrity, conduct document QA, and generate evidence-based response letters. Use when Codex is asked to revise a manuscript after peer review, manage a revision workbook, audit citations or document consistency, verify revisions, or prepare reviewer responses and final revision deliverables.
---

# Manuscript Revision

Assist a senior researcher while preserving scientific integrity, exact
traceability, and human control. Follow `AGENTS.md` and use the revision
workbook or project database as the single source of truth for every comment,
decision, change, verification result, and response.

## Load the references

- Read [workflow.md](references/workflow.md) before planning or executing a
  manuscript revision.
- Read [integrity-rules.md](references/integrity-rules.md) before interpreting
  evidence, revising scientific claims, or reporting completion.
- Read [highlight-policy.md](references/highlight-policy.md) before applying or
  checking highlights.
- Read
  [response-letter-style.md](references/response-letter-style.md) before
  drafting or checking a response letter.

## Required inputs

Require the following inputs in a confidential local workspace:

1. The authoritative source manuscript and its format.
2. The exact editor and reviewer comments.
3. A project manifest using safe project metadata.
4. Journal instructions, required template, and citation style when available.
5. Verified references or an author-approved reference source.
6. Experimental records, analyses, and result status for claims affected by
   revision.
7. Author decisions and approvals recorded at the applicable gates.

Also collect prior-round responses, supplements, figure source files, and
reference libraries when they are necessary to verify the current round. Do
not copy confidential inputs into Git.

Stop intake if the authoritative manuscript or reviewer comments are missing
or unreadable.

## Required outputs

Produce, when requested and supported by verified inputs:

1. A highlighted revised manuscript.
2. A clean revised manuscript.
3. A revision workbook or project database.
4. A response-to-reviewers letter.
5. A final quality-assurance report.
6. A machine-readable audit log.

Keep each output marked as draft until its release checks and required
approvals pass.

## Single source of truth

Create one record per reviewer comment and assign a stable identifier such as
`R1-C01`. Preserve the exact comment text. At minimum, keep these linked fields:

- stable identifier;
- reviewer and sequence number;
- exact comment;
- interpretation;
- required action;
- proposed and applied manuscript change;
- supporting evidence;
- manuscript location;
- highlight color;
- owner or approver;
- status and verification result; and
- response-letter entry.

Update the source-of-truth record before propagating a verified state to other
deliverables. Never let a response letter or manuscript annotation become an
independent status system.

## Separate reasoning from deterministic processing

Use reasoning for:

- interpreting reviewer intent;
- identifying scientific or rhetorical gaps;
- mapping comments to manuscript sections;
- proposing revision options;
- assessing whether evidence supports a claim;
- drafting source-grounded revisions and responses; and
- identifying ambiguity, conflict, or need for human judgment.

Use deterministic file-processing tools for:

- extracting and preserving document text and structure;
- assigning and checking identifiers;
- editing DOCX structures and applying exact highlight values;
- updating workbook cells and database records;
- checking references, numbering, cross-references, hashes, and diffs;
- generating files from approved records; and
- rendering documents for visual inspection.

Do not delegate exact file mutation, formatting verification, or consistency
checks to unsupported prose inference. A reasoned proposal is not an applied
file change.

## Execute the phased workflow

Follow all twelve phases in order; see
[workflow.md](references/workflow.md) for entry criteria, actions, and exit
criteria.

1. Intake and project manifest.
2. Reviewer-comment inventory.
3. Gap analysis.
4. Revision planning.
5. Human approval.
6. Section-by-section revision.
7. Reference lock.
8. Experimental integrity validation.
9. Structural and visual QA.
10. Response-letter generation.
11. Cross-document consistency.
12. Final release.

Return to an earlier phase whenever new evidence or an approved change
invalidates downstream work. Do not state that a change is complete until it
has been applied and verified.

## Use only allowed status values

Use only these values for reviewer-comment and revision records:

- `pending`: inventoried but not yet analyzed;
- `needs-evidence`: supporting evidence is missing or insufficient;
- `needs-clarification`: reviewer intent or author direction is ambiguous;
- `planned`: an action and verification method have been proposed;
- `awaiting-approval`: the proposal is at a required human gate;
- `approved`: the recorded proposal has explicit human approval;
- `in-progress`: an approved action is being applied;
- `applied`: the change exists in the working manuscript but is not verified;
- `verified`: the applied change and its linked records have passed checks;
- `rejected`: an explicitly human-approved decision not to perform the request;
- `blocked`: the item cannot safely proceed.

Never use `verified` for a proposal, generated draft, or uninspected file.
Record rejected items with rationale, evidence, approver, and an appropriate
response-letter entry.

## Enforce approval gates

Pause and obtain explicit human approval:

1. After the revision plan and before substantive manuscript edits.
2. Before accepting or changing a novelty claim.
3. Before accepting an experimental conclusion.
4. Before accepting a statistical interpretation.
5. Before rejecting, declining, or partially addressing a reviewer request.
6. Before final release.

Treat approval as invalidated if the underlying evidence or scientific meaning
materially changes.

## Stop safely

Stop the affected item and set an appropriate non-final status when:

- evidence required to support a claim is missing;
- reviewer intent is scientifically consequential and ambiguous;
- source documents conflict;
- a requested change would require fabrication or unsupported inference;
- the exact reviewer comment cannot be preserved;
- confidential material is inside or about to enter Git;
- a required deterministic processor fails or produces an unverifiable result;
- a required approval is absent; or
- cross-document records disagree.

Block final release if any critical item remains unresolved. Report the exact
blocker and the human decision or source needed to proceed.

## Perform final-release checks

Before requesting final approval:

- confirm every reviewer comment has a stable identifier and allowed status;
- confirm every non-rejected request is applied and verified;
- confirm every rejected or partial response has explicit human approval;
- lock and audit references and citations;
- validate experimental values, statistical statements, and affected claims
  against authoritative evidence;
- confirm figures, tables, equations, captions, numbering, and
  cross-references;
- render and visually inspect every page of every Word deliverable;
- reconcile the manuscript, source of truth, and response letter field by
  field;
- confirm locations and highlight colors from the rendered manuscript;
- confirm all outputs remain labeled draft until final human approval; and
- record approval and release results in the audit log.

Release only when all checks pass and the human final-release gate is approved.
