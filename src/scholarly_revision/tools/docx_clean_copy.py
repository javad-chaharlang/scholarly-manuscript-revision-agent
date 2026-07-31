'''Create clean DOCX copies without removing unrelated author highlighting.'''

from __future__ import annotations

from pathlib import Path

from docx import Document

from scholarly_revision.tools.docx_highlight_manager import remove_revision_highlights
from scholarly_revision.tools.docx_reader import read_docx


def document_text_signature(path: str | Path) -> tuple[str, ...]:
    return tuple(record.text for record in read_docx(path))


def validate_text_equivalence(first: str | Path, second: str | Path) -> bool:
    return document_text_signature(first) == document_text_signature(second)


def create_clean_copy(
    highlighted_path: str | Path,
    clean_path: str | Path,
) -> tuple[Path, int]:
    source = Path(highlighted_path).expanduser().resolve()
    destination = Path(clean_path).expanduser().resolve()
    if source == destination:
        raise ValueError('clean copy destination must differ from highlighted source')
    document = Document(source)
    removed = remove_revision_highlights(document)
    destination.parent.mkdir(parents=True, exist_ok=True)
    document.save(destination)
    if not validate_text_equivalence(source, destination):
        raise ValueError('highlighted and clean manuscript text is not equivalent')
    return destination, removed
