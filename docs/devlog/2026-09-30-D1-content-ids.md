# D1 · Content IDs

- **Author:** Venkata Sai Karthik
- **Date:** 2026-09-30
- **Card:** [D1](../development/workplan.md) · **Issue:** [#11](https://github.com/evalhawk/evalhawk/issues/11) · **PR:** [#23](https://github.com/evalhawk/evalhawk/pull/23)

## What I built

`src/evalhawk/core/ids.py`:

- `content_id(obj) -> str`: a 64-character fingerprint of any JSON-style value
- `normalize_text(text) -> str`: converts `\r\n` and `\r` line endings to `\n`
- `MAX_DEPTH = 100`: the deepest nesting `content_id` accepts

## The idea, simply

A content ID is like a library barcode **calculated from the words inside the book**.
Two copies of the same book get the same barcode, one changed word gives a different
barcode, and every library in the world calculates the same one without a central list.

EvalHawk uses these fingerprints to recognise the same question, answer or judge setup
anywhere. That's what gives us no duplicate imports, never paying an AI judge twice for
the same judgment, and train/dev/test piles that are the same on every machine.

How it works:

```
Python value      {"b": 1, "a": "x"}
  │ check structure   (dict keys are text? no deeper than 100 levels?)
  │ json.dumps        (canonicalize: sorted keys, no spaces, UTF-8, no NaN)
  ▼
JSON text         '{"a":"x","b":1}'
  │ .encode("utf-8") → bytes → SHA-256 → .hexdigest()
  ▼
ID                "cdab067e…4246"
```

`content_id` first checks the structure recursively: dict keys must be strings, it may
be at most 100 levels deep, and any error includes the **path** to the problem (`$` is the
top, so `$.outer[0]` means "first item of the list under `outer`"). Then it
**canonicalizes** the value with `json.dumps` (sorted keys, no spaces, UTF-8, no NaN or
Infinity), so equal data always becomes identical text. That text is encoded to UTF-8
bytes and hashed with SHA-256.

- **Dict key order doesn't matter;** list order and value types do (`1`, `1.0`, `True`
  and `"1"` all get different IDs).
- **Any one-character change** gives a completely different ID (the avalanche effect).
- Separately, `normalize_text` fixes line endings. Callers use it on **text files such as
  prompt templates**, so a template saved on Windows gets the same ID as on Linux. It is
  not applied inside `content_id`, because user data from JSONL already has stable line
  breaks, and a hashing function shouldn't silently change what it's given.

## How I know it's right

27 tests in `tests/unit/core/test_ids.py`, in six groups:

1. **Golden tests:** four fixed inputs must always give the same exact hashes. The expected
   values were computed with `hashlib` on hand-written JSON, **independently of our code**.
2. **Same content → same ID,** including a Hypothesis property test that tries about 100
   random dictionaries with their keys in both orders.
3. **Different content → different ID:** one letter, list order, and value types.
4. **Bad data is refused loudly:** NaN and Infinity, non-string keys (also nested), sets, bytes.
5. **Line endings:** a Windows and a Linux copy of the same template get the same ID.
6. **Deep nesting:** 100 levels work, 101 are refused, and 5,000 give our clear error
   rather than Python's `RecursionError`.

I also **sabotaged the code on purpose**: I removed `sort_keys=True` and exactly the three
predicted tests failed (Hypothesis found its own counter-example). That proves the tests
really check something.

## What surprised me / gotchas

- **`json.dumps({1: "a"})` silently turns the key `1` into `"1"`.** So `{1: "a"}` and
  `{"1": "a"}` would get the same ID: a hidden collision. We refuse non-string keys instead.
- **NaN isn't equal to itself** (`nan != nan`), and it isn't valid JSON, so it can't have a
  stable identity.
- **The order of `.replace()` calls matters:** replacing `\r` before `\r\n` would turn a
  Windows line break into two line breaks.
- **Python's recursion limit is about 1,000**, and it's shared with whoever called us, so
  the point where deep data fails would vary. An explicit `MAX_DEPTH` makes it predictable.
- **The hash is of text, not of the Python object:** the object becomes canonical JSON
  text, then bytes, and only the bytes are hashed.
- **This is a one-way door** (ADR-0006). Once IDs are stored in users' databases, changing
  how they're computed breaks everything, which is why the golden tests freeze them.

## How AI helped (and where it was wrong)

Claude Code explained the concepts, wrote the tests first and then the code, and ran all
the checks. I asked it to justify each part: why line endings are normalized outside
`content_id`, what `path="$"` means, how each `json.dumps` option changes the output, and
how nested IDs chain together. My question about deep nesting led to measuring the real
recursion limit and adding `MAX_DEPTH`. Nothing it produced had to be corrected, but its
first version had no depth limit until I asked.

## Learn more

- [ADR-0006: Content-addressed IDs and immutable splits](../decisions/0006-content-addressed-ids-and-splits.md)
- Python docs: [`json.dumps`](https://docs.python.org/3/library/json.html#json.dumps), [`hashlib`](https://docs.python.org/3/library/hashlib.html)
- [SHA-2 on Wikipedia](https://en.wikipedia.org/wiki/SHA-2)
- How Git uses the same idea: [Git internals: Git objects](https://git-scm.com/book/en/v2/Git-Internals-Git-Objects)
