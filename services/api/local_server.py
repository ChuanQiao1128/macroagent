from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, TextIO
from urllib.parse import urlparse

from pydantic import ValidationError

from services.api import AnalyzePhotoFacadeRequest, analyze_photo_facade

_HEALTH_PATH = "/health"
_ANALYZE_PATH = "/v1/meals/analyze-photo"
_SUPPORTED_PATHS = {_HEALTH_PATH, _ANALYZE_PATH}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m services.api.local_server",
        description=(
            "Run a local HTTP server exposing deterministic photo analysis "
            "for on-device smoke tests."
        ),
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host/interface to bind (use 0.0.0.0 for LAN access).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="TCP port to listen on.",
    )
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


class LocalAnalyzePhotoHandler(BaseHTTPRequestHandler):
    server_version = "MacroAgentLocalHTTP/1.0"

    def send_error(
        self,
        code: int,
        message: str | None = None,
        explain: str | None = None,
    ) -> None:
        del explain
        if code == HTTPStatus.NOT_IMPLEMENTED:
            self._handle_unsupported_method()
            return
        super().send_error(code, message=message)

    def do_GET(self) -> None:
        path = _normalize_path(self.path)
        if path == _HEALTH_PATH:
            self._write_json(HTTPStatus.OK, {"status": "ok"})
            return

        if path == _ANALYZE_PATH:
            self._write_method_not_allowed(["POST"])
            return

        self._write_path_not_found(path)

    def do_POST(self) -> None:
        path = _normalize_path(self.path)
        if path == _HEALTH_PATH:
            self._write_method_not_allowed(["GET"])
            return
        if path != _ANALYZE_PATH:
            self._write_path_not_found(path)
            return

        body_text = self._read_body_text()
        if body_text is None:
            return

        try:
            body = json.loads(body_text)
        except json.JSONDecodeError as exc:
            self._write_error(
                HTTPStatus.BAD_REQUEST,
                code="invalid_json",
                message="request body must be valid JSON",
                details={
                    "line": exc.lineno,
                    "column": exc.colno,
                    "position": exc.pos,
                },
            )
            return

        try:
            request = AnalyzePhotoFacadeRequest.model_validate(body)
        except ValidationError as exc:
            self._write_error(
                HTTPStatus.BAD_REQUEST,
                code="invalid_schema",
                message="request body does not match AnalyzePhotoFacadeRequest",
                details=_format_validation_errors(exc),
            )
            return

        response = analyze_photo_facade(request)
        self._write_json(HTTPStatus.OK, response.model_dump(mode="json"))

    def do_DELETE(self) -> None:
        self._handle_unsupported_method()

    def do_HEAD(self) -> None:
        self._handle_unsupported_method()

    def do_OPTIONS(self) -> None:
        self._handle_unsupported_method()

    def do_PATCH(self) -> None:
        self._handle_unsupported_method()

    def do_PUT(self) -> None:
        self._handle_unsupported_method()

    def log_message(self, _format: str, *args: object) -> None:  # noqa: A003
        # Keep test and CLI output deterministic.
        del args

    def _handle_unsupported_method(self) -> None:
        path = _normalize_path(self.path)
        if path not in _SUPPORTED_PATHS:
            self._write_path_not_found(path)
            return
        if path == _HEALTH_PATH:
            self._write_method_not_allowed(["GET"])
            return
        self._write_method_not_allowed(["POST"])

    def _read_body_text(self) -> str | None:
        content_length_raw = self.headers.get("Content-Length")
        if content_length_raw is None:
            self._write_error(
                HTTPStatus.BAD_REQUEST,
                code="invalid_json",
                message="missing Content-Length header",
            )
            return None

        try:
            content_length = int(content_length_raw)
        except ValueError:
            self._write_error(
                HTTPStatus.BAD_REQUEST,
                code="invalid_json",
                message="Content-Length must be an integer",
            )
            return None

        if content_length <= 0:
            self._write_error(
                HTTPStatus.BAD_REQUEST,
                code="invalid_json",
                message="request body must not be empty",
            )
            return None

        payload = self.rfile.read(content_length)
        try:
            return payload.decode("utf-8")
        except UnicodeDecodeError:
            self._write_error(
                HTTPStatus.BAD_REQUEST,
                code="invalid_json",
                message="request body must be UTF-8 JSON",
            )
            return None

    def _write_method_not_allowed(self, allowed_methods: list[str]) -> None:
        self._write_error(
            HTTPStatus.METHOD_NOT_ALLOWED,
            code="unsupported_method",
            message=f"method {self.command!r} is not supported for this path",
            details={"allowed_methods": allowed_methods},
            headers={"Allow": ", ".join(allowed_methods)},
        )

    def _write_path_not_found(self, path: str) -> None:
        self._write_error(
            HTTPStatus.NOT_FOUND,
            code="unsupported_path",
            message=f"path {path!r} is not supported",
        )

    def _write_error(
        self,
        status: HTTPStatus,
        *,
        code: str,
        message: str,
        details: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "error": {
                "code": code,
                "message": message,
            }
        }
        if details is not None:
            payload["error"]["details"] = details
        self._write_json(status, payload, headers=headers)

    def _write_json(
        self,
        status: HTTPStatus,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        if headers is not None:
            for key, value in headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(encoded)


def run_server(host: str, port: int, *, stderr: TextIO | None = None) -> int:
    err = stderr or sys.stderr

    with ThreadingHTTPServer((host, port), LocalAnalyzePhotoHandler) as server:
        err.write(f"listening on http://{host}:{port}\n")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            err.write("received interrupt, shutting down\n")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    return run_server(args.host, args.port)


def _normalize_path(raw_path: str) -> str:
    return urlparse(raw_path).path or "/"


def _format_validation_errors(exc: ValidationError) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    for error in exc.errors(include_url=False):
        details.append(
            {
                "type": str(error.get("type", "validation_error")),
                "loc": [str(part) for part in error.get("loc", ())],
                "msg": str(error.get("msg", "invalid value")),
            }
        )
    return details


if __name__ == "__main__":
    raise SystemExit(main())
