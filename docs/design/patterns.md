# Design patterns and intuitions

This page is evalhawk's **low-level design (LLD)**: the patterns the code uses and the
intuitions behind them. The rules themselves are in the [engineering standards](../development/standards.md).

## The picture in one paragraph

Think of evalhawk as a restaurant. **`core/` and `stats/`** are the recipes: pure knowledge
that never touches an appliance. **Adapters** (`judges/`, `targets/`, `sources/`,
`storage/`) are the appliances, and you can swap brands. **`services/`** is the head chef,
who runs a dish from start to finish. **`wiring.py`** is the person who plugs the appliances
in on opening day, and the only one who knows which brands you bought. **`cli/`** and
**`ui/`** are the waiters: they take orders and present results, but never cook.

```
cli, ui ──► wiring ──► services ──► runner ──► core, stats
                  └──► judges, targets, sources, storage ──► core (and stats)
```

## Patterns

| # | Pattern | Simple picture | Where in evalhawk |
|---|---|---|---|
| 1 | **Ports and adapters** | A wall socket: any plug that fits works | Ports: `core/protocols.py`. Adapters: `judges/`, `targets/`, `sources/`, `storage/` |
| 2 | **Protocol (structural typing)** | "If it quacks like a Judge, it's a Judge" | Users' judges need only `judge_id` and `async judge()`, with no inheritance ([ADR-0004](../decisions/0004-protocols-and-helper-base-classes.md)) |
| 3 | **Template method** (optional helper) | A form with blanks: we do the boring parts | `judges/base.py`: we render, parse and hash; the subclass writes the model call |
| 4 | **Decorator** | A phone case: same shape, extra layer | `CachedJudge`, `RecalibratedJudge`, `RedactingJudge` each wrap a Judge and are a Judge |
| 5 | **Composite** | A team that acts as one player | `CascadeJudge(cheap, strong)` is itself a Judge, so cascades nest |
| 6 | **Strategy** | Same job, choose the method | Estimator (Rogan-Gladen or PPI), label-queue strategy |
| 7 | **Registry and factory** | A phone book from name to class | `plugins.py`: `type = "openai_compatible"` in TOML becomes a class; entry points for third parties |
| 8 | **Composition root / dependency injection** | Plug everything in once, at the front door | `wiring.py`. Services receive a Judge; they never build one |
| 9 | **Repository** | A librarian: ask for books, not shelf numbers | The `Store` protocol. Services never see SQL |
| 10 | **Functional core, imperative shell** | The math never touches the outside world | `stats/` is pure; I/O lives at the edges |
| 11 | **Value objects** | A banknote: defined by its contents, immutable | Frozen models; `Estimate` validates itself when created |
| 12 | **Content-addressed IDs** | A fingerprint | sha256 IDs give idempotency, caching and reproducibility ([ADR-0006](../decisions/0006-content-addressed-ids-and-splits.md)) |

## What happens when you run `evalhawk eval`

1. `cli/` parses the arguments.
2. `config.py` loads and validates `evalhawk.toml`.
3. `wiring.py` builds the Store, the Target and the Judges (wrapping each judge in `CachedJudge`).
4. `services/evaluate.py` checks the data shape and assigns and locks splits, then passes
   the jobs to `runner/`.
5. `runner/` calls the Target and the Judges concurrently, with retries and a budget.
6. The Store saves traces and verdicts.
7. `services/estimate.py` loads arrays from the Store and calls `stats/`, which returns an `Estimate`.
8. `cli/` prints `0.781 [0.742, 0.816] (ppi, n=412, unknown=1.2%)`.

## Ten intuitions

### 1. Imports point inward

A lamp is built to fit the wall socket, but the wall knows nothing about lamps. Inner code
(domain and math) must not know that outer code (databases, APIs, CLI) exists.

```python
# Wrong: stats/correction.py
from evalhawk.storage.sqlite import SQLiteStore  # math now depends on a database

# Right: services/estimate.py fetches arrays, then calls pure math
judge_test, judge_cal, human_cal = store.load_arrays(criterion_id, judge_id)
estimate = corrected_pass_rate(judge_test, judge_cal, human_cal, rng=rng)
```

Quick test: could you delete `storage/` and still `import evalhawk.stats`? If so, the
direction is right.

### 2. Three kinds of code

**Data** (what things *are*: `Verdict`, `Estimate`), **doing** (the steps of a task:
`services/`), and **talking to the world** (HTTP, disk, SQL: adapters). If one file does
two of these, split it. Warning signs: a model with a `.save()` method, or a judge that
computes intervals.

### 3. Anything you can't control is passed in

Randomness, time, network and disk come in as parameters. A test kitchen uses an oven
with a guaranteed temperature, so a failure is the recipe's fault.

```python
# Wrong: a different interval on every run
def bootstrap_ci(x):
    rng = np.random.default_rng()


# Right: the caller decides; the seed goes in the run manifest
def bootstrap_ci(x, *, rng: np.random.Generator) -> Estimate: ...
```

### 4. Numbers travel with their uncertainty

"v1 = 82%, v2 = 85%" means nothing without n. With 50 examples the 95% ranges are roughly
69–90% and 73–93%, so you can't tell the versions apart. With 2,000 examples they're about
±1.7 points, and you probably can. A bare number hides the one fact the decision needs.

Three sources of doubt go into evalhawk's intervals: **sampling** (which examples you
tested), **judge error** (estimated from a limited number of human labels), and
**correlation** (related questions are not independent evidence).

So statistics functions return an `Estimate`, never a `float`, and decisions use the
interval, not the points:

```python
def decide(diff: Estimate) -> str:  # diff = v2 - v1, paired
    if diff.low > 0:
        return "BETTER"
    if diff.high < 0:
        return "WORSE"
    return "INCONCLUSIVE"  # the interval includes zero: collect more data
```

### 5. Wrap, don't modify

To add behaviour to a judge, wrap it in another object that is *also* a Judge (the
decorator pattern). The wrapper accepts **anything shaped like a Judge**, not one specific
class, so wrappers can wrap wrappers, and they work on users' own judges.

```python
class CachedJudge:
    def __init__(self, inner: Judge, store: Store) -> None:
        self.inner, self.store = inner, store

    @property
    def judge_id(self) -> str:
        return self.inner.judge_id  # same answers, so the same ID

    async def judge(self, trace: Trace, criterion: Criterion) -> Verdict:
        if hit := self.store.get_verdict(trace.id, criterion.id, self.judge_id):
            return hit
        verdict = await self.inner.judge(trace, criterion)
        self.store.put_verdict(verdict)
        return verdict


judge = CachedJudge(RecalibratedJudge(CascadeJudge(jev, ollama)), store)
```

With inheritance, five judges and four optional features would need up to 80 subclasses.
With wrappers they need nine classes. Two rules follow:

- **A wrapper that changes the answers must change the `judge_id`** (`RecalibratedJudge`,
  `CascadeJudge`). A wrapper that changes only how answers are obtained (caching, timing,
  retries) keeps it.
- **Order matters.** `Timed(Cached(j))` measures what the caller experiences, including
  fast cache hits. `Cached(Timed(j))` caches the first call's latency. That's why stacking
  lives in one place: `wiring.py`.

### 6. Fail loud, fail early

An airport checks your passport at check-in, not after you land. Check data shapes when
you load them, not 400 paid calls later. Refuse to correct with a judge that is too weak,
instead of printing a wild number. `Estimate` validates itself, so a bug crashes in a test
and never reaches a report.

### 7. Same input, same ID, same result

IDs are fingerprints of content. Importing twice creates no duplicates. A one-word prompt
change gives a new `judge_id`, so old verdicts are never wrongly reused. A crashed run
resumes where it stopped. Hash a *canonical* form (sorted keys, LF line endings), or
identical content gets different IDs.

### 8. Write the fake first

Pilots train in a simulator where the weather is controlled. A `FakeJudge` with known
sensitivity 0.80 and specificity 0.90, on data with a known true pass rate of 0.70, tells
you exactly what the corrected interval should contain. With a real LLM, you can't tell a
math bug from a model quirk. Fakes are free, fast and offline, and they ship in
`evalhawk.testing` for users too.

### 9. Keep the public API small

A restaurant menu versus its kitchen. Only what `evalhawk/__init__.py` exports is a
promise. Everything else can be refactored freely. Anything on the menu needs a CHANGELOG
entry to change, and after 1.0 a major version bump.

### 10. One reason to change per module

Prompt text lives in `judges/templates/*.md`, not inside `openai_compat.py`, so a wording
tweak and an HTTP retry fix never touch the same file. Test: describe the module's job in
one sentence without the word "and".
