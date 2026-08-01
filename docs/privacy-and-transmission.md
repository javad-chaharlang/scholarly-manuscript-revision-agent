# Privacy and AI transmission

The application uses local storage, but semantic Codex tasks are not described
as offline processing. The UI therefore shows both statements:

- Local storage
- AI transmission requires approval

## What stays local

Original manuscript and reviewer files, complete manuscript structure,
unselected sections, original experimental datasets, confidential
attachments, author notes, project state, deterministic QA artifacts, rendered
pages, and run audit records stay in the private project workspace. The
application does not use an API key, expose Codex authentication tokens, add
telemetry, or send webhooks.

## What can be transmitted

Only the exact redacted payload visible in Review Context can be transmitted.
Depending on task policy it can contain selected exact reviewer comments,
selected paragraph excerpts, approved action records, and narrowly linked
evidence, result, reference, change, or response records. The manifest shows
the character count and hash of every local input used to construct it.

No task runs merely because context exists. The author must check the
confirmation box and record `APPROVE_TRANSMISSION`. Modifying context clears
prior approval. A retry also requires a new approval.

## Redaction

The context builder removes sensitive fields and patterns for author email,
phone number, postal address, private notes, local absolute paths, journal
login data, API keys, tokens, passwords, secrets, and credentials. It excludes
hidden document metadata, original datasets, and unapproved confidential
attachments. Redactions are listed in the manifest.

Redaction is a safeguard, not a substitute for author review. Before approval,
inspect the exact transmitted payload, ensure every excerpt is necessary, and
use Modify Context to remove excess material. Prefer minimal comment context
for interpretation and a small exact section for drafting.

## Audit confidentiality

Raw model output and the complete prompt package are confidential project
artifacts. They are stored under `agent_runs`, not in general application
logs or Git. Export Package creates a local audit ZIP; treat it as confidential
and do not attach it to issues or commits.

Cancellation stops the subprocess when possible. Content already transmitted
cannot be recalled, so context review must happen before approval.
