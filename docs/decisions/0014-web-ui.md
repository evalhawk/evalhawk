# ADR-0014: A local web UI behind the `[ui]` extra

- **Status:** Proposed (awaiting approval by both maintainers)
- **Date:** 2026-11-01
- **Deciders:** Venkata Sai Karthik, Krishna Nandimandalam

## Context

Corrected numbers need human labels, and labelling must be fast and **blind** (the judge's
verdict is never shown, to avoid anchoring). A terminal is poor for reading long answers
and contexts. The plan named FastAPI, Jinja2 and htmx as an optional extra.

## Decision

- `pip install "evalhawk[ui]"` adds **FastAPI ≥ 0.162, Uvicorn ≥ 0.54, Jinja2 ≥ 3.1.6**
  (checked on PyPI 2026-11-01). The core install is unchanged.
- **htmx 2.0.11** is vendored as one static file (0BSD licence; downloaded from unpkg and
  jsDelivr, identical SHA-256 `d6fdc75f…f717`). No JavaScript build step.
- Form posts are parsed with the standard library (`urllib.parse.parse_qs`), so
  `python-multipart` is **not** needed.
- `evalhawk ui` binds to **127.0.0.1** by default and refuses POSTs whose `Origin` or
  `Referer` host differs from the server's, so another site open in the browser cannot
  submit labels (cross-site request forgery).
- The label queue offers only **dev representatives** (one answer per locked group,
  repeat 0), in a stable per-annotator shuffle, so every label counts in the report and
  any prefix is a random sample (inclusion probability 1). The page shows the input,
  reference, contexts and answer; it never shows the verdict, reasoning, judge or version.
- Tests use FastAPI's `TestClient` with **httpx2** (dev only), which Starlette now prefers
  over `httpx`.

## Consequences

**Positive**

- Labelling is fast (P/F/U keys, auto-advance), blind by construction and tested as such.
- No new core dependencies; the UI is opt-in.

**Negative**

- Three optional dependencies to keep current.
- Uncertainty- or disagreement-first queues are not offered yet: they need weighted (IPW)
  inference in the report, which currently accepts only inclusion probability 1.

## Alternatives considered

| Option | Why not |
|---|---|
| Standard-library `http.server` | Hand-rolled routing, templating and escaping; more risk for little gain |
| A JavaScript front end (React/Vue) | A build toolchain for a local labelling tool |
| CLI-only labelling | Poor for long answers and contexts; slower |
