# Limitations

Honest numbers need honest limits. These are the assumptions EvalHawk's results depend on,
and the cases it doesn't handle. Each will be revisited as the project matures.

## Statistical assumptions

| Assumption | What breaks if it's false | What EvalHawk does |
|---|---|---|
| **Rogan-Gladen:** the judge's error rates are the same on the labeled set and on the data being estimated | The correction is biased | Offers PPI as an alternative, and flags a calibration as stale when the two disagree |
| **PPI:** the labeled set is a random sample of the same data | The correction is biased | Records each item's inclusion probability and applies inverse-probability weights for non-random queues |
| **The judge is better than chance** (sensitivity + specificity > 1) | The correction explodes | Refuses to correct when sensitivity + specificity − 1 ≤ 0.1 |
| **Examples are independent, or grouped by `group_id`** | Intervals are too narrow | Cluster-robust intervals when `group_id` is set; you must set it for related questions |
| **Human labels are the truth** | Everything is calibrated against a flawed reference | Blind labeling reduces anchoring; multi-annotator agreement is planned |

## Scope limits

- **Binary criteria only** (PASS, FAIL, UNKNOWN). Graded quality must be split into several
  yes/no criteria ([ADR-0003](decisions/0003-binary-criteria-only.md)).
- **Few labels give wide intervals.** With about 50 human labels, expect intervals several
  points wide. EvalHawk tells you, rather than hiding it.
- **Single-turn and RAG first.** Pairwise, multi-turn and agent trajectories come later.
- **One writer at a time.** The default SQLite store suits one machine. Keep `.evalhawk/` on
  a local disk, not a network drive or a cloud-synced folder such as OneDrive
  ([ADR-0001](decisions/0001-sqlite-default-store.md)).
- **Probabilities need logprobs.** Calibration metrics (ECE, Brier) are only available for
  judges whose provider returns token log-probabilities.
- **Free-tier providers may train on your data.** Don't send private data through them.
