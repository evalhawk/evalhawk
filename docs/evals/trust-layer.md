# The trust layer

!!! info "Planned"
    Phases 1–3 (math, storage, reports), 5 (labeling UI) and 7 (CI gate).

Every system page ends with "you get a corrected pass rate with an error range". This page
explains what happens between the judge's verdicts and that number. It works the same way
for **every** criterion: code checks, built-in templates, custom questions, and DeepEval
metrics.

## The problem it solves

An AI judge says **82%** of your answers pass. Three things are wrong with that number:

1. **The judge makes mistakes.** It passes some bad answers and fails some good ones.
2. **It's a sample.** A different set of test questions gives a different number.
3. **Changes look bigger than they are.** 82% → 85% may be noise.

## Step by step

### 1. You label a small sample, blind

`evalhawk label` opens a local page showing one answer at a time. Press **P** (pass),
**F** (fail) or **U** (unsure). The judge's verdict is **never shown**, so it can't
influence you. About 100 labels per criterion is a good start; EvalHawk tells you when
you need more.

Labels come from the **train** and **dev** splits only. The **test** split is locked and
reserved for the final report ([ADR-0006](../decisions/0006-content-addressed-ids-and-splits.md)).

### 2. EvalHawk grades the judge

Comparing the judge with your labels gives the judge's **report card** for that criterion:

```text
Judge "local" on no_fabrication    (n = 100 human labels)
  catches good answers (sensitivity)   95%  [89% – 98%]
  catches bad answers  (specificity)   60%  [45% – 73%]
  agreement beyond chance (kappa)      0.58 [0.41 – 0.72]
  status                               ✅ ok
```

The status becomes **⚠ insufficient** with too few labels, and **❌ stale** when the judge's
model, prompt or settings change, because a changed judge is a different judge.

### 3. EvalHawk corrects the pass rate

Using the report card, the judge's 82% is corrected for its known mistakes:

```text
no_fabrication   judge says 82%  →  corrected 76%  [70% – 82%]   (rogan_gladen, n=1000)
```

Two correction methods are available. **Rogan-Gladen** (1978) works backwards from the
judge's error rates. **Prediction-powered inference** (Angelopoulos et al., 2023) subtracts
the judge's average error measured on your labels. If they disagree, EvalHawk warns you,
because an assumption is probably broken ([Limitations](../limitations.md)).

If the judge is barely better than chance, EvalHawk **refuses** to correct and tells you
why, rather than printing a meaningless number.

### 4. Every number gets an honest error range

The range includes the uncertainty from your test sample **and** from the judge's
measured error rates. It's widened automatically when answers are related (the same
`group_id`) or repeated runs of the same input.

### 5. Versions are compared statistically

```text
evalhawk compare --base v1 --candidate v2

no_fabrication   +6.0 points [+2.1, +9.8]   BETTER
polite           +0.8 points [-2.5, +4.1]   CAN'T TELL YET (need ~900 more examples)
```

Answers are **paired** by input, so only the inputs where v1 and v2 disagree count. That
makes the comparison far more sensitive than comparing two averages. In CI,
`evalhawk compare` exits with code 1 only for a **significant** regression.

## Methods and sources

| Step | Method | Source |
|---|---|---|
| Report card | Sensitivity, specificity, Cohen's kappa, Wilson intervals | Cohen (1960); Wilson (1927) |
| Correction | Rogan-Gladen; prediction-powered inference | Rogan & Gladen (1978); [Angelopoulos et al. (2023)](https://arxiv.org/abs/2301.09633) |
| Error ranges | Wilson intervals; bootstrap; clustered errors | [Miller (2024)](https://arxiv.org/abs/2411.00640) |
| Comparison | Exact McNemar test; paired bootstrap; power analysis | McNemar (1947); Miller (2024) |
| Unbiased smart labeling | Inverse-probability weighting | Horvitz & Thompson (1952) |
| Judge confidence | Reliability diagram, ECE, Brier; Platt and isotonic recalibration | [Guo et al. (2017)](https://arxiv.org/abs/1706.04599); Platt (1999) |

Full details are in [architecture §7 and §13](../architecture.md#7-statistics-core-specification).
