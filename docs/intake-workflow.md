# Deterministic reviewer-document intake

Phase 3 creates a confidential local revision project from a required reviewer
DOCX and an optional manuscript DOCX or PDF. It performs no network access,
OCR, OpenAI API call, scientific interpretation, or manuscript revision.

## Confidentiality boundary

The workspace root must be outside this Git repository. Input files are copied;
the originals are never moved or altered. The manifest contains safe project
metadata and copied file names only. File size, SHA-256, role, relative storage
path, and copy timestamp are recorded in the intake report. Reviewer text is
stored only in the local `working/reviewer_comments.json` and workbook.

The fixed project layout is:

```text
<workspace-root>/<project-slug>/
??? input/
??? working/
?   ??? reviewer_comments.json
??? outputs/
?   ??? Revision_Master.xlsx
??? rendered/
??? audit/
?   ??? intake_report.json
??? config/
    ??? project_manifest.yaml
```

## DOCX extraction

The reader emits body paragraphs and table-cell paragraphs in document order.
Each record includes exact text, style name, order index, and zero-based table,
row, and cell indices when applicable. Missing, unreadable, empty, and invalid
DOCX files fail with explicit errors. Images are not processed and OCR is not
used.

The parser recognizes reviewer, editor, general, and numbered comment headings.
It preserves comment text exactly and stores whitespace-normalized text in a
separate field only when normalization changes the value. Separate comments are
split only at explicit numbered or recognized structural boundaries. Generic
unnumbered boundaries are retained as deterministic records and marked
`manual_review_required: true`; they are not interpreted or paraphrased.

Stable IDs and highlights follow repository policy:

| Source | ID pattern | Highlight |
|---|---|---|
| Reviewer 1 | `R1-C01` | `YELLOW` |
| Reviewer 2 | `R2-C01` | `BRIGHT_GREEN` |
| Editor | `ED-C01` | `VIOLET` |
| General/shared | `GEN-C01` | `VIOLET` |

## Command line

```powershell
python scripts/create_revision_project.py `
  --workspace-root C:\path\outside\repository `
  --project-name anonymous-revision `
  --manuscript-id SYNTHETIC-ID `
  --reviewer-file C:\path\reviewer-comments.docx `
  --manuscript-file C:\path\manuscript.docx `
  --journal "UNSPECIFIED" `
  --reviewer-count 2
```

`--manuscript-file`, `--journal`, and `--reviewer-count` are optional. An
existing project is refused unless `--force` is explicitly supplied. Force
replaces only the exact slugged project directory below the supplied workspace
root. Console output is limited to workspace/output paths, counts, and warnings;
reviewer or manuscript content is never printed.

## Workbook status

`Revision_Master.xlsx` is a macro-free draft source of truth with the eleven
required sheets, enum-backed data validation, formulas, filters, frozen headers,
wrapped text, and the exact three-color highlight legend. Intake does not claim
that comments have been analyzed, planned, applied, verified, or approved.
Manual-review flags and warnings must be resolved against the authoritative
reviewer file before later workflow phases rely on those boundaries.
