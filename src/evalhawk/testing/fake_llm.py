"""A local fake of an OpenAI-compatible chat API, for testing judges and targets offline.

Example:
    >>> with FakeLLMServer() as server:  # doctest: +SKIP
    ...     server.respond = lambda payload: (200, chat_reply("VERDICT: PASS"))
    ...     judge = OpenAICompatibleJudge(base_url=server.url, model="any")
"""

import json
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Self

Responder = Callable[[dict[str, Any]], tuple[int, dict[str, Any]]]


def chat_reply(
    text: str,
    *,
    top_logprobs: list[dict[str, Any]] | None = None,
    prompt_tokens: int = 100,
    completion_tokens: int = 10,
) -> dict[str, Any]:
    """A minimal chat-completions response body."""
    choice: dict[str, Any] = {"index": 0, "message": {"role": "assistant", "content": text}}
    if top_logprobs is not None:
        choice["logprobs"] = {
            "content": [{"token": "x", "logprob": 0, "top_logprobs": top_logprobs}]
        }
    return {
        "choices": [choice],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
    }


class FakeLLMServer:
    """Serve ``POST /v1/chat/completions`` on 127.0.0.1, recording every request.

    Set ``respond`` to decide each reply as ``(status, json_body)``. Use as a context
    manager, or call :meth:`start` and :meth:`stop`.
    """

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.headers: list[dict[str, str]] = []
        self.respond: Responder = lambda _payload: (200, chat_reply("VERDICT: PASS"))
        self.url = ""
        self._server: ThreadingHTTPServer | None = None

    def start(self) -> Self:
        state = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                state.requests.append(payload)
                state.headers.append({k.lower(): v for k, v in self.headers.items()})
                status, body = state.respond(payload)
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, format: str, *args: object) -> None:
                pass  # keep output quiet

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}/v1"
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def __enter__(self) -> Self:
        return self.start()

    def __exit__(self, *args: object) -> None:
        self.stop()
