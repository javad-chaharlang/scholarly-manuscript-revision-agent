from hashlib import sha256
from pathlib import Path

import pytest

from phase7_helpers import make_ready_phase7_project
from scholarly_revision.tools.release_package_builder import build_release_package


def test_release_package_hashes_allowlist_and_overwrite_refusal(tmp_path: Path) -> None:
    root = make_ready_phase7_project(tmp_path)
    (root / 'outputs' / 'confidential-notes.txt').write_text('excluded', encoding='utf-8')
    (root / 'input' / 'original-reviewer-file.docx').write_bytes(b'excluded')
    result = build_release_package(root, 'release_v001')
    names = {item.release_path for item in result.manifest.artifacts}
    assert names == {
        'Revised_Manuscript_Highlighted.docx',
        'Revised_Manuscript_Clean.docx',
        'Response_to_Reviewers.docx',
        'Revision_Master.xlsx',
        'Final_QA_Report.xlsx',
        'Final_Release_Report.json',
    }
    assert 'confidential-notes.txt' not in names
    assert 'original-reviewer-file.docx' not in names
    for artifact in result.manifest.artifacts:
        released = result.package_path / artifact.release_path
        assert sha256(released.read_bytes()).hexdigest() == artifact.sha256
    assert result.manifest_path.is_file()
    with pytest.raises(FileExistsError):
        build_release_package(root, 'release_v001')


def test_release_package_versions_are_immutable_siblings(tmp_path: Path) -> None:
    root = make_ready_phase7_project(tmp_path)
    first = build_release_package(root, 'release_v001')
    second = build_release_package(root, 'release_v002')
    assert first.package_path != second.package_path
    assert first.package_path.is_dir() and second.package_path.is_dir()
