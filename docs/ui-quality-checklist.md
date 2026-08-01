# Phase 9 manual UI quality checklist

Record the tester, date, Streamlit version, operating system, workspace, and
synthetic project ID for every run. Use anonymous synthetic data only.

## Viewports and layout

- [ ] Desktop layout reviewed at the tester's normal resolution.
- [ ] 1366 × 768: navigation, shell, workflow stepper, forms, and tables fit.
- [ ] 1920 × 1080: content does not become excessively sparse or wide.
- [ ] Narrow window: responsive rows wrap and remain operable.
- [ ] No horizontal overflow on primary pages.
- [ ] No clipped buttons, labels, dialogs, tables, or download controls.
- [ ] No hidden workflow stages; disabled future stages remain identifiable.

## Theme, language, and accessibility

- [ ] Light theme contrast and focus states reviewed.
- [ ] Dark theme contrast and focus states reviewed.
- [ ] English UI contains consistent English labels.
- [ ] Persian UI uses RTL labels while manuscript/reviewer content direction is unchanged.
- [ ] Keyboard traversal reaches navigation, filters, actions, and confirmations.
- [ ] Status is communicated by text/icon as well as color.
- [ ] Reviewer Yellow, Bright Green, and Violet appear only in controlled reviewer badges/highlights.
- [ ] Click targets are large enough and destructive actions require confirmation.

## Content stress cases

- [ ] Long reviewer comments remain readable in the master-detail layout.
- [ ] Large project list can be searched, filtered, sorted, and resumed.
- [ ] Empty states explain the next safe action.
- [ ] Loading states use `st.status` for long-running operations.
- [ ] Failure states show readable redacted errors.
- [ ] Blocked states remain visually prominent.
- [ ] Tables remain usable with long IDs, hashes, and section names.

## Workflow and artifacts

- [ ] Required and optional wizard files are clearly distinguished.
- [ ] Zero-byte, empty reviewer, and invalid DOCX files are rejected.
- [ ] Reruns do not duplicate project outputs or decisions.
- [ ] Invalid future actions remain disabled.
- [ ] Plan, text, QA, visual, and final-release approvals are never inferred.
- [ ] Every required artifact has a working download action when permitted.
- [ ] Visual-QA controls cover all five mandatory artifacts.
- [ ] Release remains blocked until every mandatory check and approval passes.
- [ ] Generated Word documents are rendered and inspected page by page before release.

