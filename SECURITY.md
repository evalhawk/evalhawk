# Security policy

## Supported versions

evalhawk is pre-release. Only the latest version on `main` (and, once published, the latest
release on PyPI) receives security fixes.

## Reporting a vulnerability

**Please don't report security issues in public GitHub issues, discussions or pull requests.**

Use GitHub's private vulnerability reporting instead:

1. Go to the repository's [**Security** tab](https://github.com/evalhawk/evalhawk/security).
2. Click **Report a vulnerability**.
3. Describe the issue, how to reproduce it, and its impact.

Only the maintainers can see the report. We aim to acknowledge it within 7 days and to
agree a fix and disclosure timeline with you. We're happy to credit you in the release
notes if you'd like.

## What's in scope

evalhawk runs locally, but it handles sensitive things. We especially want to hear about:

- **Secrets leaking:** API keys (read from environment variables) appearing in the database,
  logs, run manifests, exports or error messages.
- **Data sent to the wrong place:** traces or labels reaching an endpoint the user didn't
  configure, or the `redact` hook being bypassed.
- **Unsafe config handling:** `${ENV}` expansion or HTTP target templates that allow
  injection, or TLS verification being silently disabled.
- **The labeling UI** (when it exists): it binds to localhost; anything that exposes it or
  allows cross-site requests against it.
- **Untrusted input:** crafted JSONL, CSV or trace files that cause code execution or
  write outside the project directory.

Out of scope: vulnerabilities in third-party model providers, or in data the user
deliberately sends to them.
