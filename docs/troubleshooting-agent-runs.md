# Troubleshooting Codex agent runs

Use Agent Settings to re-detect capabilities and test the authenticated CLI.
Use `python scripts/check_codex_health.py` for the same local-only check.
The optional `--live` smoke test sends anonymous synthetic text and should be
run only by an explicit operator decision.

## Installation and authentication

- `CODEX_NOT_INSTALLED`: set the executable path or install Codex, then
  re-detect. No task is marked complete.
- `NOT_AUTHENTICATED`: run `codex login` outside the application and test
  again. Authentication credentials are never displayed or stored.
- `AUTHORIZATION_403`: refresh the authenticated session and retry only by
  explicit user action.
- `CLI_VERSION_MISMATCH`: inspect `codex exec --help`. The bridge never
  guesses unsupported flags.

## Execution failures

- `NETWORK_TIMEOUT` or `TASK_TIMEOUT`: inspect stderr and duration, reduce
  context if appropriate, then use Retry with Instruction. Retries never run
  automatically.
- `USER_CANCELLED`: confirm the task and run are cancelled. Create a retry
  only if the semantic work is still needed.
- `GLOBAL_CONCURRENCY_LIMIT`: another semantic task is active. Wait for it or
  cancel it; one active task per project and one global worker are the defaults.
- `RECOVERY_REQUIRED`: the application found an abandoned RUNNING record.
  Inspect its run directory and choose cancel or explicit retry. It is never
  resumed automatically.

## Input and output failures

- `MISSING_INPUT_FILE` or `SOURCE_HASH_MISMATCH`: do not run against stale
  context. Restore the expected input or prepare and approve a new context.
- `MALFORMED_OUTPUT`: inspect `raw_stdout.txt`, `raw_stderr.txt`, and
  `raw_output.json` when present. The output was not imported.
- `SCHEMA_VALIDATION_FAILED`: inspect `validation_report.json`. Common
  causes are missing requested comments, unknown IDs, extra fields, invented
  evidence or references, unsupported numbers, completion claims, and
  unverified page or line locations.
- Duplicate task: open the existing task. If it failed or was rejected, use
  Retry with Instruction instead of silently duplicating it.
- Stale project state: return to the required deterministic workflow page and
  complete its explicit gate before importing semantic output.

## Inspect and recover

Open Agent Tasks, select the task, and use View Raw Output, View Validated
Output, or Export Package. Compare `task.json`, `context_manifest.json`,
`prompt_hash.txt`, `validation_report.json`, `author_decision.json`, and
`run_manifest.json`. Confidential prose is intentionally absent from the
general application log.

Restarting Streamlit does not remove task history. If the page appears stale,
use Refresh Project; status polling reads the disk registry. Do not edit task
or run JSON by hand, infer approval, or relabel a failed run as complete.

## Safe connection checks

Test Codex Connection performs only local version, help, and login-status
commands. Run Safe JSON Smoke Test is an explicit live action from Settings
and sends only the anonymous health sentence documented in the script. Normal
tests mock the CLI and never make live model calls.
