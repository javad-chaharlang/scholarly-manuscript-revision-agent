from hashlib import sha256
from pathlib import Path

from scholarly_revision.tools.manuscript_structure_reader import read_manuscript_structure

FIXTURE = Path(__file__).parent / 'fixtures' / 'synthetic_manuscript.docx'


def test_structure_ids_order_and_source_immutability() -> None:
    before = sha256(FIXTURE.read_bytes()).hexdigest()
    structure = read_manuscript_structure(FIXTURE)
    assert sha256(FIXTURE.read_bytes()).hexdigest() == before
    headings = [item for item in structure.elements if item.element_type == 'heading']
    assert [item.text for item in headings[:3]] == ['Abstract', 'Introduction', 'Related Work']
    assert [item.element_id for item in headings[:3]] == ['SEC-001', 'SEC-002', 'SEC-003']
    assert [item.order_index for item in structure.elements] == list(range(len(structure.elements)))
    paragraph_ids = [item.paragraph_id for item in structure.elements if item.paragraph_id]
    assert paragraph_ids == [f'PAR-{n:04d}' for n in range(1, len(paragraph_ids) + 1)]


def test_tables_figures_equations_references_and_highlights() -> None:
    structure = read_manuscript_structure(FIXTURE)
    tables = [item for item in structure.elements if item.element_type == 'table']
    figures = [item for item in structure.elements if item.element_type == 'figure_caption']
    equations = [item for item in structure.elements if item.element_type == 'equation']
    assert [item.element_id for item in tables] == ['TBL-001', 'TBL-002']
    assert all(item.caption and item.caption.startswith('Table') for item in tables)
    assert [item.element_id for item in figures] == ['FIG-001', 'FIG-002']
    assert len(equations) >= 3
    assert structure.reference_section_boundary['element_id'] == 'REF-001'
    assert any(item.highlight_colors for item in structure.elements)
    assert all(item.page_number is None for item in structure.elements)


def test_uncertain_elements_are_flagged() -> None:
    structure = read_manuscript_structure(FIXTURE)
    uncertain = [item for item in structure.elements if item.uncertain]
    assert any(item.element_type == 'possible_heading' for item in uncertain)
    assert any(item.element_type == 'equation' for item in uncertain)
