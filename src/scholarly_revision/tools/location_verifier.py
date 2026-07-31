'''Verify stable manuscript locations without inferring pages or Word lines.'''

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field

from scholarly_revision.models.response_package import LocationStatus
from scholarly_revision.services.project_workspace import sha256_file
from scholarly_revision.tools.manuscript_structure_reader import (
    ManuscriptStructure, read_manuscript_structure,
)


class LocationVerification(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    location: str
    verified: bool
    status: LocationStatus
    matched_element_ids: list[str] = Field(default_factory=list)
    reason: str | None = None


_PAGE = re.compile(r'\bpage\s+(\d+)\b', re.I)
_LINES = re.compile(r'\blines?\s+(\d+)(?:\s*[-–]\s*(\d+))?\b', re.I)
_SECTION = re.compile(r'^(?:sub)?section\s+(.+)$', re.I)
_PARAGRAPH = re.compile(r'^paragraph\s+(PAR-\d{4,})$', re.I)
_OBJECT = re.compile(r'^(table|figure|equation)\s*\(?\s*([0-9]+)\s*\)?$', re.I)
_REFERENCE = re.compile(r'^reference\s*\[\s*(\d+)\s*\]$', re.I)


def _normal(value: str) -> str:
    return re.sub(r'\s+', ' ', value).strip().casefold()


def _explicit_page_result(
    location: str,
    manuscript: Path,
    metadata: dict[str, Any] | None,
) -> LocationVerification:
    if not metadata:
        return LocationVerification(
            location=location, verified=False, status=LocationStatus.UNVERIFIED,
            reason='Rendered page metadata was not supplied; page and line values cannot be inferred.',
        )
    recorded_hash = metadata.get('manuscript_sha256') or metadata.get('source_sha256')
    if recorded_hash and str(recorded_hash) != sha256_file(manuscript):
        return LocationVerification(
            location=location, verified=False, status=LocationStatus.UNVERIFIED,
            reason='Rendered page metadata does not match the manuscript SHA-256.',
        )
    records = metadata.get('verified_locations', metadata.get('locations', {}))
    verified = False
    if isinstance(records, list):
        verified = location in records
    elif isinstance(records, dict):
        item = records.get(location)
        verified = item is True or (isinstance(item, dict) and item.get('verified') is True)
    if not verified:
        return LocationVerification(
            location=location, verified=False, status=LocationStatus.UNVERIFIED,
            reason='The exact rendered location is not explicitly verified in page metadata.',
        )
    status = (
        LocationStatus.PAGE_AND_LINES_VERIFIED
        if _LINES.search(location) else LocationStatus.PAGE_VERIFIED
    )
    return LocationVerification(location=location, verified=True, status=status)


def verify_location(
    manuscript_path: str | Path,
    location: str,
    *,
    page_metadata: dict[str, Any] | None = None,
    structure: ManuscriptStructure | None = None,
) -> LocationVerification:
    '''Verify one exact structural or explicitly rendered location.'''

    manuscript = Path(manuscript_path).expanduser().resolve()
    if not location or not location.strip():
        return LocationVerification(
            location=location, verified=False, status=LocationStatus.UNVERIFIED,
            reason='Location is blank.',
        )
    exact = location.strip()
    if _PAGE.search(exact) or _LINES.search(exact):
        return _explicit_page_result(exact, manuscript, page_metadata)
    structure = structure or read_manuscript_structure(manuscript)

    paragraph = _PARAGRAPH.fullmatch(exact)
    if paragraph:
        target = paragraph.group(1).upper()
        matches = [
            element.element_id for element in structure.elements
            if element.paragraph_id == target
        ]
        return LocationVerification(
            location=exact, verified=bool(matches),
            status=LocationStatus.OBJECT_VERIFIED if matches else LocationStatus.UNVERIFIED,
            matched_element_ids=matches,
            reason=None if matches else 'Paragraph ID is absent from the manuscript structure.',
        )

    section = _SECTION.fullmatch(exact)
    if section:
        target = _normal(section.group(1))
        matches = [
            str(item['section_id']) for item in structure.outline
            if _normal(str(item['title'])) == target
            or _normal(str(item['title'])).startswith(target + ' ')
            or _normal(str(item['title'])).startswith(target + '.')
        ]
        return LocationVerification(
            location=exact, verified=bool(matches),
            status=LocationStatus.SECTION_VERIFIED if matches else LocationStatus.UNVERIFIED,
            matched_element_ids=matches,
            reason=None if matches else 'Section or subsection heading is absent.',
        )

    obj = _OBJECT.fullmatch(exact)
    if obj:
        kind, number = obj.group(1).casefold(), obj.group(2)
        pattern = re.compile(rf'^\s*{kind}(?:ure)?\s*{number}\b', re.I)
        matches = [
            element.element_id for element in structure.elements
            if (
                (kind == 'table' and element.element_type in {'table', 'table_caption'})
                or (kind == 'figure' and element.element_type == 'figure_caption')
                or (kind == 'equation' and element.element_type == 'equation')
            ) and (
                pattern.search(element.caption or element.text)
                or (kind == 'equation' and re.search(rf'\(\s*{number}\s*\)\s*$', element.text))
            )
        ]
        return LocationVerification(
            location=exact, verified=bool(matches),
            status=LocationStatus.OBJECT_VERIFIED if matches else LocationStatus.UNVERIFIED,
            matched_element_ids=list(dict.fromkeys(matches)),
            reason=None if matches else f'{kind.title()} {number} is absent.',
        )

    reference = _REFERENCE.fullmatch(exact)
    if reference:
        number = reference.group(1)
        matches = [
            element.element_id for element in structure.elements
            if element.element_type == 'reference_entry'
            and re.match(rf'^\s*\[?{number}\]?\s*[.)]?', element.text)
        ]
        return LocationVerification(
            location=exact, verified=bool(matches),
            status=LocationStatus.OBJECT_VERIFIED if matches else LocationStatus.UNVERIFIED,
            matched_element_ids=matches,
            reason=None if matches else f'Reference [{number}] is absent.',
        )

    return LocationVerification(
        location=exact, verified=False, status=LocationStatus.UNVERIFIED,
        reason='Unsupported or unverifiable location; use a stable section or object identifier.',
    )


def verify_locations(
    manuscript_path: str | Path,
    locations: Iterable[str],
    *,
    page_metadata: dict[str, Any] | None = None,
) -> list[LocationVerification]:
    structure = read_manuscript_structure(manuscript_path)
    return [
        verify_location(
            manuscript_path, location, page_metadata=page_metadata, structure=structure
        )
        for location in locations
    ]
