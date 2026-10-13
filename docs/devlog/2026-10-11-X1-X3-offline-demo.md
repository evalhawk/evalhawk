# X1-X3: Offline demo and streaming statistics glue

**Date:** 2026-10-11
**Maintainers:** Krishna Nandimandalam and Venkata Sai Karthik (pairing)
**Status:** Implemented locally; human review and public dataset acceptance pending.

## What we built

Recorded JSONL/CSV annotation import, resumable run manifests, scalar Store reads,
dev calibration/test reports, latest-reviewer majority voting, paired proxy comparison,
sample planning for independent pairs, audit tables and an offline support-bot demo.
SQLite schema 2 upgrades schema 1 without rewriting immutable split assignments.
Rich stays at the CLI boundary; new ADRs 0011/0012 are Proposed, not accepted.

## What I learned

- A version name is not a run ID; resume must retain execution identity.
- Grouped test bootstrap does not make IID calibration or PPI clustered.
  Representative-case selection makes the narrower estimand explicit.
- Byte arrays are only part of memory usage: ID maps, conversions and bootstrap
  gathers matter. Batches adapt to temporary workspace, not total process memory.
- SQLite virtual generated columns can be added to populated tables; stored generated
  columns cannot be added with ALTER TABLE. JSON remains the source of truth.
- Majority adjudication and missingness assumptions must be visible, not hidden.

## How AI was used

GitHub Copilot implemented and tested the authorized plan, explained assumptions,
and drafted these notes. The humans still need to inspect every line, verify the
tests, review both tracks and approve ADRs. No commit, push or merge was performed.

## Local verification and observed results

- Full suite: 335 passed, including slow simulations and million-item memory tests.
- Fast coverage suite: 312 passed, 23 deselected; 92% overall, core/stats target met.
- Ruff lint/format, pyright, four import contracts, strict docs, lockfile and wheel
  build passed. Wheel inspection confirmed both SQL migrations and service modules.
- A populated schema-1 database upgrades without losing verdicts or labels.
- Default seed 0: v1 naive/Rogan-Gladen/PPI = 0.766/0.736/0.697;
  v2 = 0.792/0.743/0.729. Separate test truth = 0.695/0.774 (includes UNKNOWN cases).
  Correction is not guaranteed to be closer for every finite sample.
- Overall judge-proxy comparison: +0.027, 95% CI [-0.024, 0.080], INCONCLUSIVE.
  Billing: -0.112, CI [-0.201, -0.022], WORSE. Tag intervals are not simultaneous.
- Independent demo (`--paraphrases 1`): McNemar p=0.3511; 411 usable pairs.
  A 0.05 target effect at 80% power plans 871 total / 460 additional pairs.
- Default audit: 600/1152/1248 train/dev/test examples (three per independent case);
  test outcome reads include run, judge and tag provenance.
- Windows blocked the executable launcher; `uv run python -m evalhawk` successfully
  ran the real CLI workflow. Development environment and demo files stayed outside
  OneDrive. This is an environment workaround, not a resolved Windows launcher issue.

## Review checklist

- [ ] Walk through import -> Store -> scalar rows -> adjudication -> statistics -> CLI.
- [ ] Review representative-population and proxy-comparison limitations in ADR-0011.
- [ ] Review direct Rich dependency and boundary rules in ADR-0012.
- [ ] Run the offline walkthrough and compare reports with the separate answer key.
- [ ] Review populated-upgrade, repeated-import, audit, adjudication and memory tests.
- [ ] Follow up with a public human-labelled dataset and verified DeepEval examples.