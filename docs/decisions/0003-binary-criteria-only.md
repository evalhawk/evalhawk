# ADR-0003: Binary criteria only

- **Status:** Accepted
- **Date:** 2026-09-27
- **Deciders:** EVSGoud

## Context

LLM evaluations often use 1–5 or 1–10 scales. Those labels are inconsistent between
annotators and cluster in the middle. Worse, the statistics evalhawk relies on
(sensitivity and specificity, Rogan-Gladen correction, McNemar's test, PPI on a
proportion) are defined for **binary** outcomes.

A judge asked "is this answer good?" mixes several failure modes, so nobody can tell
which one it caught.

## Decision

- Every criterion is **one yes/no question about one failure mode**, e.g. "Is every factual
  claim in the answer supported by the provided context?"
- Outcomes are `PASS`, `FAIL` or `UNKNOWN`, for judges and humans alike.
- `UNKNOWN` is stored but **excluded from the estimators**, and its rate is **always
  reported** next to every estimate.
- Calibration (sensitivity, specificity, calibration curve) belongs to a
  **(judge, criterion)** pair, never to a judge alone.
- A judge may grade several criteria in one call (`MultiCriterionJudge.judge_many`), but
  each criterion still gets its own verdict.

## Consequences

**Positive**

- Every estimator in `stats/` operates on 0/1 arrays: simple, well understood, validated.
- Humans label faster and more consistently when forced to decide.
- The error analysis maps directly to criteria: one failure mode becomes one criterion
  and one calibration.

**Negative**

- Graded quality ("how helpful, 1–5?") is not supported. Users must break it into several
  binary criteria.
- More criteria means more judge calls. `judge_many` and caching reduce the cost.

## Alternatives considered

| Option | Why not |
|---|---|
| Likert scales | Inconsistent labels; the correction methods don't apply directly |
| Continuous scores with a threshold | The threshold hides a binary decision anyway; better to make it explicit |
| Two outcomes only (no `UNKNOWN`) | Forces a guess on genuinely ambiguous cases, which adds noise to the labels |

## References

- Hamel Husain, *Using LLM-as-a-Judge*: <https://hamel.dev/blog/posts/llm-judge/>
- Shankar et al., *Who Validates the Validators?* <https://arxiv.org/abs/2404.12272>
