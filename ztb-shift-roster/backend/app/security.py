"""Local-browser protections.

Binding to 127.0.0.1 keeps other machines out, but any web page open in the user's browser
can still send requests to localhost. These checks stop such pages from changing data:

* Host allowlist: blocks DNS-rebinding (a hostile domain resolving to 127.0.0.1).
* Origin check: a state-changing request carrying a foreign ``Origin`` is refused.
* Custom header: state-changing API calls must send ``X-ZTB-Request: 1``. Browsers will not
  attach a custom header cross-origin without a CORS preflight, and CORS only allows the
  local frontend origins, so plain HTML forms and cross-site fetches cannot satisfy it.

None of this is user authentication: any local process running as the same OS user can
still call the API. See docs/SECURITY.md.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
CSRF_HEADER = b"x-ztb-request"
CSRF_VALUE = b"1"

SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"cross-origin-opener-policy", b"same-origin"),
    (b"cross-origin-resource-policy", b"same-origin"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
    (
        b"content-security-policy",
        b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        b"img-src 'self' data:; font-src 'self' data:; connect-src 'self'; "
        b"object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
    ),
]


def _host_without_port(host: str) -> str:
    host = host.strip().lower()
    if host.startswith("["):  # IPv6 literal, e.g. [::1]:8000
        return host[1 : host.find("]")] if "]" in host else host
    return host.rsplit(":", 1)[0] if ":" in host else host


class LocalSecurityMiddleware:
    def __init__(
        self,
        app,
        allowed_hosts: Iterable[str],
        allowed_origins: Iterable[str],
        max_body_bytes: int,
        path_limits: dict[str, int] | None = None,
    ) -> None:
        self.app = app
        self.path_limits = path_limits or {}
        self.allowed_hosts = {h.lower() for h in allowed_hosts} | {"::1"}
        self.allowed_origins = {o.lower().rstrip("/") for o in allowed_origins}
        self.max_body_bytes = max_body_bytes

    async def _reject(self, send, status: int, detail: str) -> None:
        body = json.dumps({"detail": detail}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [(b"content-type", b"application/json"), *SECURITY_HEADERS],
            }
        )
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        host = headers.get(b"host", b"").decode("latin-1")
        if _host_without_port(host) not in self.allowed_hosts:
            await self._reject(send, 400, "Invalid Host header")
            return

        method = scope["method"].upper()
        path = scope.get("path", "")
        limit = self.path_limits.get(path, self.max_body_bytes)
        if method in STATE_CHANGING_METHODS and path.startswith("/api"):
            origin = headers.get(b"origin")
            if origin is not None and origin.decode("latin-1").lower().rstrip("/") not in self.allowed_origins:
                await self._reject(send, 403, "Cross-origin request refused")
                return
            fetch_site = headers.get(b"sec-fetch-site")
            if fetch_site is not None and fetch_site not in (b"same-origin", b"same-site", b"none"):
                await self._reject(send, 403, "Cross-site request refused")
                return
            if headers.get(CSRF_HEADER) != CSRF_VALUE:
                await self._reject(send, 403, "Missing X-ZTB-Request header")
                return
            length = headers.get(b"content-length")
            if length is not None:
                try:
                    if int(length) > limit:
                        await self._reject(send, 413, "Request body too large")
                        return
                except ValueError:
                    await self._reject(send, 400, "Invalid Content-Length")
                    return

        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise BodyTooLarge()
            return message

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                existing = {k.lower() for k, _ in message.get("headers", [])}
                extra = [(k, v) for k, v in SECURITY_HEADERS if k not in existing]
                message = {**message, "headers": [*message.get("headers", []), *extra]}
            await send(message)

        try:
            await self.app(scope, limited_receive, send_with_headers)
        except BodyTooLarge:
            await self._reject(send, 413, "Request body too large")


class BodyTooLarge(Exception):
    pass
