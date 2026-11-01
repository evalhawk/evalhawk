"""JSON over HTTP on the standard library: no requests, httpx or vendor SDKs.

Judges and targets call remote models through this one function, so retry decisions,
TLS options and error messages are consistent everywhere.
"""

import json
import ssl
import urllib.error
import urllib.request
from collections.abc import Mapping

from evalhawk.core.errors import CallError


def _tls_context(verify: bool | str) -> ssl.SSLContext:
    """``True`` = system trust store, a path = custom CA bundle, ``False`` = no checks."""
    if isinstance(verify, str):
        return ssl.create_default_context(cafile=verify)
    context = ssl.create_default_context()
    if not verify:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context


def request_json(
    method: str,
    url: str,
    payload: object | None = None,
    *,
    headers: Mapping[str, str] | None = None,
    timeout: float = 60.0,
    verify: bool | str = True,
) -> object:
    """Send a JSON request and return the decoded JSON response.

    Raises:
        CallError: on HTTP errors (retryable for 429 and 5xx), network failures and
            timeouts (retryable), or a response that isn't JSON (not retryable).
    """
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request_headers = {"Accept": "application/json"}
    if data is not None:
        request_headers["Content-Type"] = "application/json"
    request_headers.update(headers or {})
    request = urllib.request.Request(url, data=data, method=method, headers=request_headers)
    try:
        with urllib.request.urlopen(
            request, timeout=timeout, context=_tls_context(verify)
        ) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:300].decode("utf-8", "replace")
        raise CallError(
            f"{method} {url} returned HTTP {exc.code}: {detail}",
            retryable=exc.code == 429 or exc.code >= 500,
        ) from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise CallError(f"{method} {url} failed: {exc}", retryable=True) from exc
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CallError(f"{method} {url} returned a response that is not JSON") from exc
