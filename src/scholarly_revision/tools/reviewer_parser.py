'''Rule-based reviewer-comment extraction with exact-text preservation.'''

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable

from scholarly_revision.models.enums import ReviewerSource
from scholarly_revision.models.reviewer import ReviewerComment
from scholarly_revision.tools.docx_reader import DocxRecord


class ReviewerParseError(ValueError):
    '''Raised when deterministic extraction cannot produce a valid inventory.'''


@dataclass(frozen=True, slots=True)
class ReviewerParseResult:
    comments: tuple[ReviewerComment, ...]
    warnings: tuple[str, ...] = ()


@dataclass(slots=True)
class _CommentBlock:
    source: ReviewerSource
    reviewer_number: int | None
    explicit_sequence: int | None
    parts: list[str]
    manual_review_required: bool = False


_COMBINED_HEADING = re.compile(
    r'^\s*Reviewer\s*#?\s*(?P<reviewer>\d+)\s*,?\s*'
    r'Comment\s*(?P<sequence>\d+)\s*'
    r'(?:(?::|\.|-)\s*(?P<text>.*))?\s*$',
    re.IGNORECASE,
)
_REVIEWER_HEADING = re.compile(
    r'^\s*Reviewer\s*#?\s*(?P<reviewer>\d+)\s*:?\s*$',
    re.IGNORECASE,
)
_NUMBERED_COMMENT = re.compile(
    r'^\s*Comment\s*(?P<sequence>\d+)\s*'
    r'(?:(?::|\.|-)\s*(?P<text>.*))?\s*$',
    re.IGNORECASE,
)
_EDITOR_GENERAL_HEADING = re.compile(
    r'^\s*(?P<source>Editor|General)\s+Comments?\s*'
    r'(?:(?::|\.|-)\s*(?P<text>.*))?\s*$',
    re.IGNORECASE,
)
_AMBIGUOUS_HEADING = re.compile(
    r'^\s*(?:Comments?|Ambiguous\s+Block)\s*'
    r'(?:(?::|\.|-)\s*(?P<text>.*))?\s*$',
    re.IGNORECASE,
)


def _normalized_text(value: str) -> str | None:
    normalized = ' '.join(unicodedata.normalize('NFKC', value).split())
    return normalized if normalized != value else None


def _prefix(source: ReviewerSource, reviewer_number: int | None) -> str:
    if source is ReviewerSource.EDITOR:
        return 'ED'
    if source is ReviewerSource.GENERAL:
        return 'GEN'
    assert reviewer_number is not None
    return f'R{reviewer_number}'


def _trim_boundary_blanks(parts: list[str]) -> list[str]:
    start = 0
    end = len(parts)
    while start < end and parts[start] == '':
        start += 1
    while end > start and parts[end - 1] == '':
        end -= 1
    return parts[start:end]


def parse_reviewer_comments(
    records: Iterable[DocxRecord],
) -> ReviewerParseResult:
    '''Parse headings without paraphrasing, merging, or LLM inference.'''

    comments: list[ReviewerComment] = []
    warnings: list[str] = []
    used_sequences: dict[str, set[int]] = {}
    context_source: ReviewerSource | None = None
    context_reviewer: int | None = None
    current: _CommentBlock | None = None

    def start(
        source: ReviewerSource,
        reviewer_number: int | None,
        explicit_sequence: int | None = None,
        text: str | None = None,
        manual: bool = False,
    ) -> _CommentBlock:
        if source is ReviewerSource.REVIEWER and reviewer_number not in {1, 2}:
            raise ReviewerParseError(
                'repository highlight policy supports only Reviewer 1 and '
                'Reviewer 2 during deterministic intake'
            )
        parts = [text] if text is not None and text != '' else []
        return _CommentBlock(
            source=source,
            reviewer_number=reviewer_number,
            explicit_sequence=explicit_sequence,
            parts=parts,
            manual_review_required=manual,
        )

    def finalize(block: _CommentBlock) -> None:
        parts = _trim_boundary_blanks(block.parts)
        if not parts or not any(part.strip() for part in parts):
            warnings.append('A detected comment heading had no comment text.')
            return
        original = '\n'.join(parts)
        prefix = _prefix(block.source, block.reviewer_number)
        used = used_sequences.setdefault(prefix, set())
        sequence = block.explicit_sequence
        manual = block.manual_review_required
        if sequence is None:
            sequence = 1
            while sequence in used:
                sequence += 1
        elif sequence in used:
            requested = sequence
            sequence = 1
            while sequence in used:
                sequence += 1
            manual = True
            warnings.append(
                f'Duplicate explicit {prefix} comment number {requested}; '
                f'assigned {prefix}-C{sequence:02d} for manual review.'
            )
        used.add(sequence)
        comments.append(
            ReviewerComment.model_validate(
                {
                    'comment_id': f'{prefix}-C{sequence:02d}',
                    'reviewer_source': block.source,
                    'reviewer_number': block.reviewer_number,
                    'sequence_number': sequence,
                    'original_comment': original,
                    'normalized_comment': _normalized_text(original),
                    'notes': (
                        'Ambiguous comment boundary; verify against the source '
                        'document.'
                        if manual
                        else None
                    ),
                    'manual_review_required': manual,
                }
            )
        )

    def finish_current() -> None:
        nonlocal current
        if current is not None:
            finalize(current)
            current = None

    for record in records:
        for line in record.text.split('\n'):
            combined = _COMBINED_HEADING.fullmatch(line)
            if combined:
                finish_current()
                context_source = ReviewerSource.REVIEWER
                context_reviewer = int(combined.group('reviewer'))
                current = start(
                    context_source,
                    context_reviewer,
                    int(combined.group('sequence')),
                    combined.group('text'),
                )
                continue

            reviewer_heading = _REVIEWER_HEADING.fullmatch(line)
            if reviewer_heading:
                finish_current()
                context_source = ReviewerSource.REVIEWER
                context_reviewer = int(reviewer_heading.group('reviewer'))
                if context_reviewer not in {1, 2}:
                    raise ReviewerParseError(
                        'repository highlight policy supports only Reviewer 1 '
                        'and Reviewer 2 during deterministic intake'
                    )
                continue

            source_heading = _EDITOR_GENERAL_HEADING.fullmatch(line)
            if source_heading:
                finish_current()
                context_source = (
                    ReviewerSource.EDITOR
                    if source_heading.group('source').lower() == 'editor'
                    else ReviewerSource.GENERAL
                )
                context_reviewer = None
                payload = source_heading.group('text')
                if payload:
                    current = start(context_source, context_reviewer, text=payload)
                continue

            numbered = _NUMBERED_COMMENT.fullmatch(line)
            if numbered:
                finish_current()
                manual = context_source is None
                source = context_source or ReviewerSource.GENERAL
                reviewer = (
                    context_reviewer
                    if source is ReviewerSource.REVIEWER
                    else None
                )
                current = start(
                    source,
                    reviewer,
                    int(numbered.group('sequence')),
                    numbered.group('text'),
                    manual,
                )
                if manual:
                    warnings.append(
                        'A numbered comment appeared before a source heading.'
                    )
                continue

            ambiguous = _AMBIGUOUS_HEADING.fullmatch(line)
            if ambiguous:
                finish_current()
                source = context_source or ReviewerSource.GENERAL
                reviewer = (
                    context_reviewer
                    if source is ReviewerSource.REVIEWER
                    else None
                )
                current = start(
                    source,
                    reviewer,
                    text=ambiguous.group('text'),
                    manual=True,
                )
                warnings.append(
                    'An unnumbered comment boundary requires manual review.'
                )
                continue

            if current is None:
                if not line.strip():
                    continue
                source = context_source or ReviewerSource.GENERAL
                reviewer = (
                    context_reviewer
                    if source is ReviewerSource.REVIEWER
                    else None
                )
                manual = context_source is None
                current = start(source, reviewer, text=line, manual=manual)
                if manual:
                    warnings.append(
                        'Text before a recognized source heading requires '
                        'manual review.'
                    )
            else:
                current.parts.append(line)

    finish_current()
    if not comments:
        raise ReviewerParseError('no reviewer comments were extracted')
    return ReviewerParseResult(tuple(comments), tuple(dict.fromkeys(warnings)))
