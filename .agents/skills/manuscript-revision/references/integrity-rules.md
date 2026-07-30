# Scientific and Data Integrity Rules

Apply these rules to every analysis, proposal, file change, status update, and
release decision.

## References and citations

- Never fabricate a reference, citation, DOI, author, title, venue, year,
  quotation, page, or bibliographic field.
- Use only a supplied source or a source whose identity and relevance have
  been verified.
- Do not cite a work merely because its title appears relevant. Verify that it
  supports the linked claim.
- Mark an unresolved citation as `needs-evidence`; do not replace it with a
  plausible-looking source.

## Experimental and quantitative evidence

- Never fabricate or estimate an experimental value. Never interpolate,
  smooth, or back-calculate a value and present it as experimentally measured.
- Perform a derived calculation only from verified inputs and an approved
  method. Label it explicitly as calculated, preserve the inputs and method,
  and never substitute it for a measured result.
- Never invent sample sizes, uncertainty, error bars, significance values,
  model metrics, baselines, controls, units, methods, or experimental
  conditions.
- Copy quantitative values from authoritative records and verify their
  transcription, units, context, and rounding.
- Do not convert a draft, simulated, preliminary, expected, or proposed result
  into a final experimental result.
- Label draft and final results distinctly in the source of truth and all
  outputs.

## Scientific claims

- Do not make unsupported quantum, AI, statistical, causal, novelty,
  generalization, state-of-the-art, performance, or superiority claims.
- Treat words such as "novel," "significant," "robust," "optimal," "first,"
  "better," "outperforms," and "superior" as claims requiring direct evidence
  and appropriate human approval.
- Preserve the distinction between observation, interpretation, hypothesis,
  and conclusion.
- Do not strengthen certainty beyond what the evidence and study design
  support.

## Truthful reporting of work

- Never state or imply that an experiment, analysis, validation, literature
  search, revision, formatting change, or QA check was performed unless it was
  actually performed and its result was verified.
- A proposed edit is not an applied edit. An applied edit is not a verified
  edit. A verified draft is not a released final artifact.
- Do not report page numbers, line numbers, section locations, highlights, or
  cross-references until they are verified in the applicable rendered
  manuscript.

## Reviewer-comment fidelity

- Preserve reviewer comments exactly, including wording and order.
- Correct only encoding artifacts that prevent faithful display. Record the
  original text, corrected display text, reason, and scope of the correction.
- Do not silently paraphrase, merge, split, omit, or reorder reviewer text.
- Assign stable identifiers and retain traceability when a multipart comment
  needs multiple revision actions.

## Escalation

- Set the affected item to `needs-evidence` when evidence is missing or
  insufficient.
- Set the affected item to `needs-clarification` when reviewer intent is
  ambiguous and the interpretation could change scientific meaning, scope, or
  required work.
- Set the affected item to `blocked` when proceeding would require fabrication,
  violate confidentiality, bypass approval, or create a false report of work.
- Present the competing interpretations, known evidence, risk, and precise
  human decision needed. Do not choose by speculation.

## Confidentiality

- Keep unpublished manuscripts, reviewer files, experimental data, author
  identities, affiliations, correspondence, and confidential reference
  annotations in the designated local workspace outside Git.
- Do not place confidential material in prompts saved to the repository,
  fixtures, logs, screenshots, examples, configuration, or issue text.
- Use anonymous synthetic fixtures for repository tests and examples.
- Do not transmit confidential content to an external service without explicit
  authorization and an approved data-handling path.
- Stop immediately if a confidential input is staged, tracked, or written to a
  repository path; report the exact exposure risk without reproducing the
  content.
