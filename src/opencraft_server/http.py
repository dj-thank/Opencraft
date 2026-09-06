from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .auth import AuthError, Principal
from .service import CanonicalWorldService, ServiceError

MAX_BODY_BYTES = 1_000_000


@dataclass(frozen=True, slots=True)
class ServerContext:
    service: CanonicalWorldService
    bootstrap_token: str
    prototype_directory: Path | None = None


class OpenCraftHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], context: ServerContext) -> None:
        self.opencraft = context
        super().__init__(address, OpenCraftHandler)


class OpenCraftHandler(BaseHTTPRequestHandler):
    server: OpenCraftHTTPServer
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:
        # Do not log paths, query strings, headers or request bodies. A caller
        # can put a credential in any of them even when authentication rejects it.
        super().log_message("OpenCraft HTTP request processed")

    def _security_headers(self, *, content_type: str) -> dict[str, str]:
        return {
            "Content-Type": content_type,
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Cross-Origin-Resource-Policy": "same-origin",
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
        }

    def _send(self, status: int, document: Any, *, content_type: str = "application/json; charset=utf-8") -> None:
        if content_type.split(";", 1)[0].endswith("json"):
            payload = json.dumps(document, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        elif isinstance(document, bytes):
            payload = document
        else:
            payload = str(document).encode("utf-8")
        self.send_response(status)
        for name, value in self._security_headers(content_type=content_type).items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _problem(self, status: int, code: str, message: str) -> None:
        self._send(status, {
            "type": f"urn:opencraft:problem:{code}",
            "title": message,
            "status": status,
            "code": code,
        }, content_type="application/problem+json; charset=utf-8")

    def _read_json(self) -> dict[str, Any]:
        if self.headers.get("Transfer-Encoding") or len(self.headers.get_all("Content-Length", [])) != 1:
            self.close_connection = True
            raise ServiceError("invalid-framing", "one Content-Length and no Transfer-Encoding are required")
        raw_length = self.headers.get("Content-Length")
        try:
            length = int(raw_length or "0")
        except ValueError as exc:
            self.close_connection = True
            raise ServiceError("invalid-content-length", "invalid Content-Length") from exc
        if length < 0 or length > MAX_BODY_BYTES:
            self.close_connection = True
            raise ServiceError("body-too-large", "request body exceeds 1 MiB", status=413)
        if self.headers.get_content_type() != "application/json":
            self.close_connection = True
            raise ServiceError("unsupported-media-type", "Content-Type must be application/json", status=415)
        try:
            def reject_constant(_value):
                raise ValueError("non-finite JSON is not allowed")
            document = json.loads(self.rfile.read(length), parse_constant=reject_constant)
        except json.JSONDecodeError as exc:
            raise ServiceError("invalid-json", "request body is not valid JSON") from exc
        if not isinstance(document, dict):
            raise ServiceError("invalid-json", "request body must be a JSON object")
        return document

    def _principal(self, *, world_id: str | None = None) -> Principal:
        authorization = self.headers.get("Authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise ServiceError("unauthorized", "Bearer session is required", status=401)
        try:
            return self.server.opencraft.service.authenticate(token, world_id=world_id)
        except AuthError as exc:
            raise ServiceError("unauthorized", str(exc), status=401) from exc

    def _is_loopback(self) -> bool:
        return self.client_address[0] in {"127.0.0.1", "::1"}

    def _route(self, method: str) -> None:
        parsed = urlsplit(self.path)
        path = parsed.path
        service = self.server.opencraft.service

        if method == "GET" and path == "/healthz":
            self._send(200, {"status": "ok", "service": "opencraft-local-reference"})
            return
        if method == "GET" and path in {"/", "/index.html", "/app.js", "/styles.css"}:
            self._serve_prototype(path)
            return

        if method == "POST" and path == "/v1/dev/worlds":
            if not self._is_loopback() or not secrets.compare_digest(
                self.headers.get("X-OpenCraft-Bootstrap", ""), self.server.opencraft.bootstrap_token
            ):
                raise ServiceError("forbidden", "valid local bootstrap token required", status=403)
            body = self._read_json()
            self._send(201, service.create_world(
                name=str(body.get("name", "")),
                owner_display_name=str(body.get("ownerDisplayName", "")),
            ))
            return

        if method == "POST" and path == "/v1/invites/redeem":
            body = self._read_json()
            self._send(200, service.redeem_invite(
                str(body.get("inviteToken", "")),
                display_name=str(body.get("displayName", "")),
            ))
            return

        if method == "POST" and path == "/v1/join/claim":
            body = self._read_json()
            self._send(200, service.claim_join_request(str(body.get("requestToken", ""))))
            return

        actor = self._principal()

        if method == "GET" and path == "/v1/world/context":
            query = parse_qs(parsed.query, keep_blank_values=False)
            regions = tuple(filter(None, query.get("region", [])))
            limit = int(query.get("limit", ["200"])[0])
            self._send(200, service.context(actor, region_ids=regions, limit=limit))
            return

        if method == "GET" and path == "/v1/world/events":
            query = parse_qs(parsed.query, keep_blank_values=False)
            after = int(query.get("after", ["0"])[0])
            limit = int(query.get("limit", ["500"])[0])
            self._send(200, service.events_after(actor, after, limit=limit))
            return

        if method == "POST" and path == "/v1/invites":
            body = self._read_json()
            self._send(201, service.create_invite(
                actor,
                role=str(body.get("role", "viewer")),
                max_uses=body.get("maxUses", 1),
                ttl_seconds=body.get("ttlSeconds", 24 * 3600),
                approval_required=body.get("approvalRequired", True),
            ))
            return

        if method == "DELETE" and path.startswith("/v1/invites/"):
            service.revoke_invite(actor, path.removeprefix("/v1/invites/"))
            self._send(204, b"", content_type="application/octet-stream")
            return

        if method == "POST" and path.startswith("/v1/join/") and path.endswith("/decision"):
            request_id = path.removeprefix("/v1/join/").removesuffix("/decision")
            body = self._read_json()
            service.decide_join_request(actor, request_id, approve=body.get("approve"))
            self._send(200, {"status": "approved" if body.get("approve") else "rejected"})
            return

        if method == "POST" and path == "/v1/agent/previews":
            body = self._read_json()
            plan = body.get("plan")
            if not isinstance(plan, dict):
                raise ServiceError("invalid-plan", "plan must be an object")
            regions = body.get("allowedRegionIds")
            if regions is not None and (not isinstance(regions, list) or not all(isinstance(item, str) for item in regions)):
                raise ServiceError("invalid-regions", "allowedRegionIds must be an array of strings")
            self._send(201, service.preview_plan(
                actor,
                agent_id=str(body.get("agentId", "")),
                document=plan,
                allowed_region_ids=regions,
            ))
            return

        if method == "POST" and path == "/v1/agent/consents":
            body = self._read_json()
            token = service.issue_consent(
                actor,
                agent_id=str(body.get("agentId", "")),
                preview_hash=str(body.get("previewHash", "")),
                ttl_seconds=body.get("ttlSeconds", 120),
            )
            self._send(201, {"consentToken": token})
            return

        if method == "POST" and path == "/v1/agent/commits":
            body = self._read_json()
            idempotency_key = self.headers.get("Idempotency-Key", "")
            self._send(200, service.commit_preview(
                actor,
                agent_id=str(body.get("agentId", "")),
                preview_hash=str(body.get("previewHash", "")),
                consent_token=str(body.get("consentToken", "")),
                idempotency_key=idempotency_key,
            ))
            return

        if method == "POST" and path == "/v1/world/undo":
            body = self._read_json()
            self._send(200, service.undo(actor, str(body.get("transactionId", ""))))
            return

        raise ServiceError("not-found", "route not found", status=404)

    def _serve_prototype(self, request_path: str) -> None:
        directory = self.server.opencraft.prototype_directory
        if directory is None:
            raise ServiceError("not-found", "prototype is not configured", status=404)
        filename = "index.html" if request_path in {"/", "/index.html"} else request_path.lstrip("/")
        if filename not in {"index.html", "app.js", "styles.css"}:
            raise ServiceError("not-found", "asset not found", status=404)
        path = (directory / filename).resolve()
        if path.parent != directory.resolve() or not path.is_file():
            raise ServiceError("not-found", "asset not found", status=404)
        content_type = {
            ".html": "text/html; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
        }[path.suffix]
        self._send(200, path.read_bytes(), content_type=content_type)

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_DELETE(self) -> None:
        self._dispatch("DELETE")

    def _dispatch(self, method: str) -> None:
        try:
            self._route(method)
        except ServiceError as exc:
            self._problem(exc.status, exc.code, str(exc))
        except (ValueError, TypeError):
            self._problem(400, "invalid-request", "request violates input constraints")
        except Exception:
            self._problem(500, "internal-error", "the request could not be completed")
