# Phase 5 revision execution workflow

Phase 5 converts first-gate-approved revision actions into exact-text drafting
packages, records a separate human approval for the text itself, and applies
only approved text to immutable DOCX copies. It performs no network access and
does not call the OpenAI API.

## Safety and source-of-truth boundary

Revision_Master.xlsx remains the source of truth. JSON artifacts are
deterministic exchange and audit records linked by comment, action, draft,
change, target, and document-version identifiers. Reviewer comments are copied
exactly from the inventory and are rejected on import if altered.

The source manuscript is opened read-only. Every run creates a verified backup,
an immutable source version when needed, and a new output version. The original
path is never saved or overwritten.

## 1. Prepare a blank drafting package

```powershell
python scripts/prepare_revision_drafts.py \
  --project-root <private-project-root>
```

Preparation writes working/revision_drafting_input.json,
working/revision_draft_template.json, and audit/drafting_report.json. Each
eligible action includes exact comments, approved action language, exact
structural target and neighboring context, evidence/reference requirements,
highlight, and unresolved questions. proposed_text is deliberately blank.
Unknown, uncertain, equation, or reference targets are blocked instead of
guessed.

## 2. Complete and strictly import drafts

```powershell
python scripts/import_revision_drafts.py \
  --project-root <private-project-root> \
  --draft-file <completed-drafts.json>
```

Import rejects unknown or unapproved actions, changed reviewer text, missing or
stale targets, source/snapshot/hash mismatches, unsupported operations, empty
replacement text, unverified absolute page/line claims, and scientific claims
without evidence links. It never repairs draft content.

## 3. Record the second approval gate

```powershell
python scripts/review_revision_texts.py \
  --project-root <private-project-root> \
  --export-template <revision-text-decisions.json>
```

After the author records one explicit decision per draft:

```powershell
python scripts/review_revision_texts.py \
  --project-root <private-project-root> \
  --decision-file <revision-text-decisions.json>
```

Supported decisions are APPROVE_TEXT, APPROVE_TEXT_WITH_MODIFICATION,
REJECT_TEXT, REQUEST_REWRITE, NEED_MORE_EVIDENCE, and DEFER_TEXT. Approval is
never inferred. Modified approval preserves author_modified_text exactly.

## 4. Approve each reviewer-comment package

Prepare one package for every reviewer/editor/general comment. Each contains
the verbatim comment, editable proposed response, and every linked exact
change. Approval is bound to source, comment, and complete-draft hashes;
shared drafts require approval under every linked comment. Decisions are
written to the audit log and `Revision_Master.xlsx`. Application is refused
until the complete `comment_approval_packet.json` exists.

## 5. Apply approved text

```powershell
python scripts/apply_approved_revisions.py \
  --project-root <private-project-root> \
  --source-manuscript <authoritative-source.docx>
```

The service rehashes and rereads the source, revalidates every target and text
hash, rejects overlapping targets, and checks target OOXML before changing
anything. Equations, fields, EndNote citations, tracked changes, hyperlinks,
embedded objects, bookmarks, comments, footnotes/endnotes, and content controls
are manual-only in this phase.

Outputs include highlighted and clean named copies, immutable version files,
JSON/CSV change logs, a document version manifest, and an application report.
Audit summaries omit manuscript text by default and retain hashes, character
counts, and word counts.

## 6. Verify outputs

```powershell
python scripts/verify_revision_outputs.py \
  --project-root <private-project-root> \
  --source-manuscript <authoritative-source.docx>
```

Verification checks source immutability, DOCX readability, highlighted/clean
text equivalence, exact system-highlight policy, removal of only system-created
highlighting, manifest hashes, verified change-log coverage, and the absence of
unapproved applied drafts.

DOCX files must also be rendered to page images and visually inspected before
any final release. Phase 5 outputs remain drafts: response-letter generation
and the final human release approval are later gates.
