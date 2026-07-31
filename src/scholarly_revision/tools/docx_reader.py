'''Read DOCX paragraphs and table-cell paragraphs without modifying the source.'''

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from zipfile import BadZipFile

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from lxml.etree import XMLSyntaxError


class DocxReadError(ValueError):
    '''Raised when a DOCX cannot be deterministically read.'''


@dataclass(frozen=True, slots=True)
class DocxRecord:
    '''One paragraph in body or table order.

    Table, row, and cell indices are zero-based. They are ``None`` for body
    paragraphs.
    '''

    order_index: int
    record_type: str
    text: str
    style_name: str | None
    table_index: int | None = None
    row_index: int | None = None
    cell_index: int | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _style_name(paragraph: Paragraph) -> str | None:
    try:
        return paragraph.style.name if paragraph.style is not None else None
    except (AttributeError, KeyError):
        return None


def read_docx(path: str | Path) -> list[DocxRecord]:
    '''Return body paragraphs and table-cell paragraphs in document order.'''

    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f'DOCX file not found: {source}')
    if not source.is_file():
        raise DocxReadError(f'DOCX path is not a readable file: {source}')
    if source.suffix.lower() != '.docx':
        raise DocxReadError(f'expected a .docx reviewer file: {source}')

    try:
        document = Document(source)
    except PermissionError as exc:
        raise DocxReadError(f'DOCX file is unreadable: {source}') from exc
    except (PackageNotFoundError, BadZipFile, XMLSyntaxError, KeyError, ValueError) as exc:
        raise DocxReadError(f'invalid DOCX file: {source}') from exc
    except OSError as exc:
        raise DocxReadError(f'unable to read DOCX file: {source}') from exc

    records: list[DocxRecord] = []
    order_index = 0
    table_index = 0
    for element in document.element.body.iterchildren():
        if element.tag == qn('w:p'):
            paragraph = Paragraph(element, document)
            records.append(
                DocxRecord(
                    order_index=order_index,
                    record_type='paragraph',
                    text=paragraph.text,
                    style_name=_style_name(paragraph),
                )
            )
            order_index += 1
        elif element.tag == qn('w:tbl'):
            table = Table(element, document)
            for row_index, row in enumerate(table.rows):
                for cell_index, cell in enumerate(row.cells):
                    for paragraph in cell.paragraphs:
                        records.append(
                            DocxRecord(
                                order_index=order_index,
                                record_type='table_cell_paragraph',
                                text=paragraph.text,
                                style_name=_style_name(paragraph),
                                table_index=table_index,
                                row_index=row_index,
                                cell_index=cell_index,
                            )
                        )
                        order_index += 1
            table_index += 1

    if not any(record.text.strip() for record in records):
        raise DocxReadError(f'DOCX file contains no readable text: {source}')
    return records
