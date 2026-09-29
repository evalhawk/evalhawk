# ADR-0008: Zensical for the documentation site

- **Status:** Accepted
- **Date:** 2026-09-27
- **Deciders:** EVSGoud

## Context

The project needs a documentation site built from Markdown in `docs/`, published to
GitHub Pages, and checked in CI. The earlier plan named Material for MkDocs. Material for
MkDocs is in maintenance mode and reaches **end of life on 5 November 2026**; its team now
develops **Zensical**, which keeps compatibility with Material projects.

## Decision

- Use **Zensical**, configured in `zensical.toml` (based on the `zensical new` template).
- Zensical is a **dev-only** dependency (the `docs` dependency group), never shipped to users.
- CI runs `zensical build --strict`, so a broken link or warning fails the build.
- `.github/workflows/docs.yml` deploys the site to GitHub Pages on every push to `main`.

## Consequences

**Positive**

- A maintained tool from the same team, with a familiar Material look.
- Config in TOML, like the rest of the project.

**Negative**

- Zensical is young (0.0.x). Expect config changes between versions; the version is pinned
  through `uv.lock`.
- Some MkDocs plugins (for example, API docs from docstrings) may not be available yet.
  Re-evaluate before Phase 9.

## Alternatives considered

| Option | Why not |
|---|---|
| Material for MkDocs | End of life on 5 November 2026 |
| Sphinx | Heavier and reStructuredText-centred; slower to write for |
| No docs site (GitHub Markdown only) | Weaker for users and for the portfolio |

## References

- End-of-life notice: <https://github.com/squidfunk/mkdocs-material/issues/8523>
- Zensical: <https://zensical.org/>
