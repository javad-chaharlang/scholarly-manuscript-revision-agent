from pathlib import Path
import shutil

from docx import Document

from scholarly_revision.services.document_version_service import (
    allocate_document_versions,
    finalize_document_versions,
)


def test_immutable_version_numbering_and_backups(tmp_path: Path) -> None:
    root = tmp_path / 'project'
    (root / 'outputs').mkdir(parents=True)
    (root / 'audit').mkdir()
    source = tmp_path / 'source.docx'
    Document().save(source)

    first = allocate_document_versions(root, source)
    assert first.source_version == 'v001'
    assert first.output_version == 'v002'
    assert first.backup_path.is_file()
    shutil.copy2(source, first.highlighted_path)
    shutil.copy2(source, first.clean_path)
    finalize_document_versions(
        root, first, applied_change_ids=['CHG-0001'],
        verification_result='VERIFIED',
    )

    second = allocate_document_versions(root, source)
    assert second.source_version == 'v001'
    assert second.output_version == 'v003'
    assert second.highlighted_path != first.highlighted_path
