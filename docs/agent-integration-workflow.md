# Codex CLI agent integration

Phase 10 adds an optional semantic lane around the authenticated local Codex
CLI. It does not use the OpenAI API directly and does not require
`OPENAI_API_KEY`. Deterministic document processors, the project state
machine, and both scientific approval gates remain authoritative.

## Trust boundary

The Streamlit process prepares a minimal, redacted context manifest. The
author reviews the exact payload and must record `APPROVE_TRANSMISSION`
before a task can be queued. A separate local Python worker starts
`codex exec` with a direct subprocess call, an explicit working directory,
stdin prompt input, a bounded timeout, and no shell.

Codex receives only the approved prompt package. It works in a per-run audit
directory under the private project and uses read-only sandboxing when the
installed CLI supports that flag. It never receives authority to edit the
source manuscript. The worker captures stdout, stderr, exit status, duration,
prompt version and hash, context hashes, and CLI capabilities.

The installed CLI is inspected at runtime. Flags such as `--json`,
`--output-schema`, `--output-last-message`, `--cd`, `--ephemeral`,
and `--sandbox` are used only when advertised by `codex exec --help`.
If structured flags are absent, the final response must be one strict JSON
object.

## Task lifecycle

`CREATED` becomes `WAITING_FOR_TRANSMISSION_APPROVAL` after context
preparation. The author may modify scope, cancel, or approve transmission.
Only an approved task reaches `CONTEXT_READY`, `QUEUED`, and `RUNNING`.
The worker persists raw output before validation. Validated output enters
`AUTHOR_REVIEW`; it is not imported until the author records
`APPROVE_IMPORT`. Rejection and retry are explicit decisions. A retry is a
new task and requires a new context review and transmission approval.

The supported semantic task types are comment interpretation, gap analysis,
revision-plan drafting, revision-text drafting, reference-need analysis,
semantic QA, response-letter drafting, and general research notes.

## Context policies

- `MINIMAL_COMMENT_CONTEXT`: exact selected comments only.
- `SECTION_CONTEXT`: selected comments and exact selected elements.
- `EXTENDED_SECTION_CONTEXT`: selected elements plus immediate neighbours.
- `RESULTS_CONTEXT`: selected records with approved result context.
- `REFERENCE_CONTEXT`: selected records with approved references.
- `RESPONSE_CONTEXT`: exact comments and verified traceability records.
- `CUSTOM_AUTHOR_APPROVED_CONTEXT`: a custom payload requiring a separate
  explicit context approval.

Every manifest lists included comments, sections, paragraph IDs, evidence,
results, references, exclusions, character count, redactions, and hashes.
Unrelated sections, hidden metadata, credentials, original datasets, and
unapproved attachments are excluded.

## Validation and import

Raw output never bypasses Pydantic validation. Unknown identifiers, incomplete
comment coverage, extra fields, automatic approval states, invented evidence
or references, unsupported numeric or experimental claims, and unverified
locations are rejected. Rejected raw output remains in the audit directory.

Gap tasks require one record per requested comment. Plan tasks remain pending
at Gate 1. Text tasks require an already approved action and remain pending at
Gate 2. Response tasks may describe only verified applied changes. Semantic QA
is a separate optional lane and never replaces deterministic QA.

## Persistent run record

Each `agent_runs/<run-id>/` directory contains the task, context manifest,
prompt, prompt hash, output schema, raw stdout and stderr, normalized raw
output when parseable, validated output when valid, validation report, author
decision, and run manifest. The Streamlit page reads this registry from disk,
so completed history survives application restarts.

Run `python scripts/check_codex_health.py` for local capability and
authentication checks. The optional `--live` form sends only anonymous
synthetic text and must be invoked deliberately.
