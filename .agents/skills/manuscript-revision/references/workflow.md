# Manuscript Revision Workflow

Use the revision workbook or project database as the single source of truth
throughout this workflow. Each phase must record its inputs, decisions,
evidence, outputs, status changes, and verification results. Return to an
earlier phase if later evidence invalidates prior work.

## 1. Intake and project manifest

Collect the authoritative manuscript, editor and reviewer files, journal
instructions, reference sources, experimental evidence, prior-round materials,
and author constraints in a confidential local workspace. Create a project
manifest from safe metadata and record file identities, versions, and result
status without placing confidential content in Git.

Exit only when the authoritative inputs are identified and readable. Stop if
the manuscript or reviewer comments are missing, if versions cannot be
distinguished, or if confidential inputs are inside Git.

## 2. Reviewer-comment inventory

Extract comments without paraphrasing or silently correcting them. Preserve the
exact source text, reviewer identity, source order, and hierarchy. Correct only
documented encoding artifacts. Assign stable identifiers such as `R1-C01` and
record each comment in the single source of truth.

Exit only when the inventory reconciles exactly with the source reviewer
files, including multipart comments and editor directives.

## 3. Gap analysis

Interpret each comment, identify the reviewer request and underlying concern,
map it to relevant manuscript sections, and compare the request with available
evidence. Record ambiguities, conflicts, missing data, citation needs,
structural issues, and integrity risks. Separate mandatory revision needs from
optional improvements.

Exit only when each comment has a recorded interpretation or an explicit
`needs-clarification` or `needs-evidence` status.

## 4. Revision planning

For every actionable comment, record the required action, proposed manuscript
change, supporting evidence, target location, highlight category, dependencies,
owner, response strategy, and verification method. Plan shared changes once
and link them to every affected comment.

Exit only when every comment has a traceable plan, a safe stopping status, or a
documented recommendation for rejection or partial acceptance.

## 5. Human approval

Present the revision plan and unresolved issues to the author. Obtain explicit
approval before substantive revision. Obtain item-specific approval for
novelty claims, experimental conclusions, statistical interpretations, and any
rejected or partially addressed reviewer request.

Record the approver, decision, scope, and date or revision context. Exit only
with the approvals required for the next actions; keep unapproved items at
`awaiting-approval` or `blocked`.

## 6. Exact-text and comment-package approval

Record one explicit researcher decision for every exact manuscript draft.
Then create one package per exact reviewer/editor/general comment containing
the verbatim comment, proposed response, and all linked proposed changes (old
text, approved new text, target, operation, and color).

The researcher may edit the response and select which text-approved drafts are
authorized. Record the decision maker, timestamp, rationale, and hashes of the
source, comment, and complete draft. Shared drafts require approval under
every linked comment. Do not mutate the manuscript until every comment has an
explicit decision and at least one exact draft is eligible.

## 7. Section-by-section revision

Revise the manuscript in a controlled section order using only approved plans
and verified evidence. Preserve scientific meaning unless a scientific change
is explicitly approved. Apply the required highlight category and update the
source-of-truth record after each file mutation.

Mark a record `applied` only when the change exists in the manuscript. Mark it
`verified` only after checking the actual manuscript text, context, formatting,
location, and evidence. Reconcile dependencies before leaving each section.

## 8. Reference lock

Resolve all citations against verified sources. Confirm bibliographic
identity, relevance, claim support, in-text citation placement, reference-list
presence, and journal style. Record added, removed, and changed references.
Lock the approved reference set so later phases cannot silently alter it.

Exit only when every cited work is verified and every reference-list entry is
accounted for. Never substitute a plausible reference for an unverified one.

## 9. Experimental integrity validation

Compare all affected values, units, sample sizes, methods, uncertainty
statements, statistical results, tables, figures, and conclusions with
authoritative experimental records. Confirm that draft or preliminary results
are not described as final. Review quantum, AI, statistical, and superiority
claims for direct evidentiary support.

Exit only when every affected result and claim is verified or explicitly
blocked. Route changed conclusions and statistical interpretations through
their human approval gates.

## 10. Structural and visual QA

Check section order, headings, pagination, numbering, captions, references,
footnotes, figures, tables, equations, hyperlinks, and cross-references. Apply
deterministic checks where possible. Render every Word deliverable and visually
inspect every page for clipping, reflow, broken layout, incorrect highlights,
and misplaced content.

Exit only after recording both structural checks and page-level visual
inspection results.

## 11. Response-letter generation

Generate each entry from the approved pre-application response and verified
source-of-truth record. Preserve researcher-approved response text exactly and
add only deterministic verified locations and change identifiers.

Keep the response letter in draft status until it has been reconciled with the
rendered manuscript.

## 12. Cross-document consistency and final release

Compare the manuscript, revision workbook or database, and response letter
field by field. Verify comment identifiers, status, change descriptions,
evidence, locations, highlights, and response claims. Confirm that shared
changes are linked consistently and that no document reports an unapplied
change.

Exit only when all discrepancies are corrected and the consistency check is
recorded as passed.

Run all final-release checks, generate the highlighted manuscript, clean
manuscript, revision workbook, response letter, QA report, and audit log, and
render and visually inspect the Word outputs. Confirm that confidential
artifacts remain outside Git.

Present the release package and unresolved-risk summary to the author. Release
only after explicit final human approval. Record the approved file identities
and release decision in the audit log.
