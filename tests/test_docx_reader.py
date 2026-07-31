from hashlib import sha256
from pathlib import Path

import pytest
from docx import Document

from scholarly_revision.tools.docx_reader import DocxReadError, read_docx


FIXTURE = Path(__file__).parent / 'fixtures' / 'synthetic_reviewer_comments.docx'


def test_extracts_paragraphs_and_table_cells_in_document_order() -> None:
    records = read_docx(FIXTURE)
    texts = [record.text for record in records]
    first_table = next(
        index for index, record in enumerate(records)
        if record.record_type == 'table_cell_paragraph'
    )
    assert texts.index('Reviewer 2, Comment 1') < first_table
    assert texts[first_table:first_table + 2] == [
        'Comment 2',
        'Please improve the table layout for the anonymous example.',
    ]
    assert texts.index('General Comment') > first_table
    assert [record.order_index for record in records] == list(range(len(records)))


def test_paragraph_style_and_table_coordinates_are_recorded() -> None:
    records = read_docx(FIXTURE)
    editor = next(record for record in records if record.text == 'Editor Comment')
    table_comment = next(record for record in records if record.text == 'Comment 2' and record.table_index is not None)
    assert editor.style_name == 'Heading 1'
    assert editor.table_index is None
    assert (table_comment.table_index, table_comment.row_index, table_comment.cell_index) == (0, 0, 0)


def test_reader_does_not_modify_source() -> None:
    before = sha256(FIXTURE.read_bytes()).hexdigest()
    read_docx(FIXTURE)
    assert sha256(FIXTURE.read_bytes()).hexdigest() == before


def test_missing_and_invalid_docx_errors_are_clear(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match='not found'):
        read_docx(tmp_path / 'missing.docx')
    invalid = tmp_path / 'invalid.docx'
    invalid.write_bytes(b'not a zip package')
    with pytest.raises(DocxReadError, match='invalid DOCX'):
        read_docx(invalid)


def test_empty_docx_is_rejected(tmp_path: Path) -> None:
    empty = tmp_path / 'empty.docx'
    Document().save(empty)
    with pytest.raises(DocxReadError, match='no readable text'):
        read_docx(empty)
