from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Sequence
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import parse_qs, urlparse

from pydantic import ValidationError

from services.api import AnalyzePhotoFacadeRequest, analyze_photo_facade
from services.storage import (
    fetch_user_daily_totals,
    fetch_user_meal_history,
    initialize_sqlite_ledger,
    insert_user_nutrition_ledger_entry,
    prepare_healthkit_export,
)

_HEALTH_PATH = "/health"
_ANALYZE_PATH = "/v1/meals/analyze-photo"
_USER_HISTORY_PATH = "/v1/users/history"
_USER_DAILY_TOTALS_PATH = "/v1/users/daily-totals"
_USER_HEALTHKIT_EXPORT_PREP_PATH = "/v1/users/healthkit-export-prep"
_SUPPORTED_PATHS = {
    _HEALTH_PATH,
    _ANALYZE_PATH,
    _USER_HISTORY_PATH,
    _USER_DAILY_TOTALS_PATH,
    _USER_HEALTHKIT_EXPORT_PREP_PATH,
}

_LEDGER_DB_ENV_VAR = "MACROAGENT_LEDGER_DB_PATH"
_DEFAULT_LEDGER_DB_PATH = Path(tempfile.gettempdir()) / "macroagent" / "local_server_ledger.sqlite3"


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

        if path == _USER_HISTORY_PATH:
            self._handle_get_user_history()
            return

        if path == _USER_DAILY_TOTALS_PATH:
            self._handle_get_user_daily_totals()
            return

        if path == _USER_HEALTHKIT_EXPORT_PREP_PATH:
            self._handle_get_user_healthkit_export_prep()
            return

        self._write_path_not_found(path)

    def do_POST(self) -> None:
        path = _normalize_path(self.path)
        if path == _HEALTH_PATH:
            self._write_method_not_allowed(["GET"])
            return

        if path == _ANALYZE_PATH:
            self._handle_analyze_photo()
            return

        if path == _USER_HISTORY_PATH:
            self._handle_post_user_history()
            return

        if path == _USER_DAILY_TOTALS_PATH:
            self._handle_post_user_daily_totals()
            return

        if path == _USER_HEALTHKIT_EXPORT_PREP_PATH:
            self._handle_post_user_healthkit_export_prep()
            return

        self._write_path_not_found(path)

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

    def _handle_analyze_photo(self) -> None:
        body = self._read_json_body()
        if body is None:
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
        self._persist_accepted_nutrition_entry(request=request, response=response)
        self._write_json(HTTPStatus.OK, response.model_dump(mode="json"))

    def _handle_get_user_history(self) -> None:
        query = _parse_query_params(self.path)
        user_id = _single_query_value(query, "user_id")
        local_date = _single_query_value(query, "local_date")
        include_inactive_raw = _single_query_value(query, "include_inactive")
        limit_raw = _single_query_value(query, "limit")

        if user_id is None:
            self._write_missing_query_param("user_id")
            return

        if include_inactive_raw is None:
            include_inactive = False
        else:
            try:
                include_inactive = _parse_bool_value(include_inactive_raw)
            except ValueError as exc:
                self._write_error(
                    HTTPStatus.BAD_REQUEST,
                    code="invalid_schema",
                    message=str(exc),
                )
                return

        limit = 100
        if limit_raw is not None:
            try:
                limit = int(limit_raw)
            except ValueError:
                self._write_error(
                    HTTPStatus.BAD_REQUEST,
                    code="invalid_schema",
                    message="query parameter 'limit' must be an integer",
                )
                return

        self._write_user_history_payload(
            user_id=user_id,
            local_date=local_date,
            include_inactive=include_inactive,
            limit=limit,
        )

    def _handle_get_user_daily_totals(self) -> None:
        query = _parse_query_params(self.path)
        user_id = _single_query_value(query, "user_id")
        local_date = _single_query_value(query, "local_date")

        if user_id is None:
            self._write_missing_query_param("user_id")
            return

        if local_date is None:
            self._write_missing_query_param("local_date")
            return

        self._write_user_daily_totals_payload(user_id=user_id, local_date=local_date)

    def _handle_get_user_healthkit_export_prep(self) -> None:
        query = _parse_query_params(self.path)
        user_id = _single_query_value(query, "user_id")
        local_date = _single_query_value(query, "local_date")

        if user_id is None:
            self._write_missing_query_param("user_id")
            return

        if local_date is None:
            self._write_missing_query_param("local_date")
            return

        self._write_user_healthkit_export_prep_payload(user_id=user_id, local_date=local_date)

    def _handle_post_user_history(self) -> None:
        body = self._read_json_body()
        if body is None:
            return

        user_id = _required_str_field(body, "user_id")
        if user_id is None:
            self._write_missing_json_field("user_id")
            return

        local_date = _optional_str_field(body, "local_date")

        include_inactive = body.get("include_inactive", False)
        if not isinstance(include_inactive, bool):
            self._write_error(
                HTTPStatus.BAD_REQUEST,
                code="invalid_schema",
                message="field 'include_inactive' must be a boolean",
            )
            return

        limit = body.get("limit", 100)
        if not isinstance(limit, int):
            self._write_error(
                HTTPStatus.BAD_REQUEST,
                code="invalid_schema",
                message="field 'limit' must be an integer",
            )
            return

        self._write_user_history_payload(
            user_id=user_id,
            local_date=local_date,
            include_inactive=include_inactive,
            limit=limit,
        )

    def _handle_post_user_daily_totals(self) -> None:
        body = self._read_json_body()
        if body is None:
            return

        user_id = _required_str_field(body, "user_id")
        local_date = _required_str_field(body, "local_date")

        if user_id is None:
            self._write_missing_json_field("user_id")
            return

        if local_date is None:
            self._write_missing_json_field("local_date")
            return

        self._write_user_daily_totals_payload(user_id=user_id, local_date=local_date)

    def _handle_post_user_healthkit_export_prep(self) -> None:
        body = self._read_json_body()
        if body is None:
            return

        user_id = _required_str_field(body, "user_id")
        local_date = _required_str_field(body, "local_date")

        if user_id is None:
            self._write_missing_json_field("user_id")
            return

        if local_date is None:
            self._write_missing_json_field("local_date")
            return

        self._write_user_healthkit_export_prep_payload(user_id=user_id, local_date=local_date)

    def _write_user_history_payload(
        self,
        *,
        user_id: str,
        local_date: str | None,
        include_inactive: bool,
        limit: int,
    ) -> None:
        try:
            history = fetch_user_meal_history(
                _ledger_database_path(),
                user_id=user_id,
                local_date=local_date,
                include_inactive=include_inactive,
                limit=limit,
            )
        except ValueError as exc:
            self._write_error(
                HTTPStatus.BAD_REQUEST,
                code="invalid_schema",
                message=str(exc),
            )
            return

        self._write_json(
            HTTPStatus.OK,
            {
                "user_id": user_id,
                "local_date": local_date,
                "include_inactive": include_inactive,
                "limit": limit,
                "entry_count": len(history),
                "entries": [entry.model_dump(mode="json") for entry in history],
            },
        )

    def _write_user_daily_totals_payload(
        self,
        *,
        user_id: str,
        local_date: str,
    ) -> None:
        try:
            totals = fetch_user_daily_totals(
                _ledger_database_path(),
                user_id=user_id,
                local_date=local_date,
            )
        except ValueError as exc:
            self._write_error(
                HTTPStatus.BAD_REQUEST,
                code="invalid_schema",
                message=str(exc),
            )
            return

        self._write_json(HTTPStatus.OK, totals.model_dump(mode="json"))

    def _write_user_healthkit_export_prep_payload(
        self,
        *,
        user_id: str,
        local_date: str,
    ) -> None:
        try:
            preparation = prepare_healthkit_export(
                _ledger_database_path(),
                user_id=user_id,
                local_date=local_date,
            )
        except ValueError as exc:
            self._write_error(
                HTTPStatus.BAD_REQUEST,
                code="invalid_schema",
                message=str(exc),
            )
            return

        self._write_json(HTTPStatus.OK, preparation.model_dump(mode="json"))

    def _persist_accepted_nutrition_entry(
        self,
        *,
        request: AnalyzePhotoFacadeRequest,
        response: Any,
    ) -> None:
        if response.status == "BLOCK" or response.nutrition is None:
            return

        local_date = _local_date_from_capture_timestamp(
            request.payload.capture_metadata.capture_timestamp
        )
        try:
            insert_user_nutrition_ledger_entry(
                _ledger_database_path(),
                user_id=request.payload.user_id,
                meal_id=f"meal:{request.payload.request_id}",
                entry_kind="accepted",
                source="deterministic",
                local_date=local_date,
                created_at=request.payload.capture_metadata.capture_timestamp,
                trace_id=response.trace_id,
                note=f"captured via local_server status={response.status}",
                kcal=response.nutrition.kcal.best_estimate,
                protein_g=response.nutrition.protein_g.best_estimate,
                carbs_g=response.nutrition.carbs_g.best_estimate,
                fat_g=response.nutrition.fat_g.best_estimate,
                sugar_g=response.nutrition.sugar_g.best_estimate,
                sodium_mg=response.nutrition.sodium_mg.best_estimate,
                fiber_g=response.nutrition.fiber_g.best_estimate,
            )
        except ValueError:
            # Keep analyze responses deterministic even when persistence fails.
            return

    def _handle_unsupported_method(self) -> None:
        path = _normalize_path(self.path)
        if path not in _SUPPORTED_PATHS:
            self._write_path_not_found(path)
            return

        if path == _HEALTH_PATH:
            self._write_method_not_allowed(["GET"])
            return

        if path == _ANALYZE_PATH:
            self._write_method_not_allowed(["POST"])
            return

        self._write_method_not_allowed(["GET", "POST"])

    def _read_json_body(self) -> dict[str, Any] | None:
        body_text = self._read_body_text()
        if body_text is None:
            return None

        try:
            payload = json.loads(body_text)
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
            return None

        if not isinstance(payload, dict):
            self._write_error(
                HTTPStatus.BAD_REQUEST,
                code="invalid_schema",
                message="request body must be a JSON object",
            )
            return None

        return payload

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

    def _write_missing_query_param(self, parameter_name: str) -> None:
        self._write_error(
            HTTPStatus.BAD_REQUEST,
            code="invalid_schema",
            message=f"missing required query parameter '{parameter_name}'",
        )

    def _write_missing_json_field(self, field_name: str) -> None:
        self._write_error(
            HTTPStatus.BAD_REQUEST,
            code="invalid_schema",
            message=f"missing required field '{field_name}'",
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


def _parse_query_params(raw_path: str) -> dict[str, list[str]]:
    return parse_qs(urlparse(raw_path).query, keep_blank_values=True)


def _single_query_value(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None
    value = values[0].strip()
    return value if value else None


def _parse_bool_value(raw_value: str) -> bool:
    value = raw_value.strip().casefold()
    if value in {"1", "true", "yes", "y"}:
        return True
    if value in {"0", "false", "no", "n"}:
        return False
    raise ValueError("query parameter 'include_inactive' must be true/false")


def _required_str_field(body: dict[str, Any], key: str) -> str | None:
    value = body.get(key)
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed if trimmed else None


def _optional_str_field(body: dict[str, Any], key: str) -> str | None:
    value = body.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed if trimmed else None


def _local_date_from_capture_timestamp(capture_timestamp: str | datetime) -> str:
    if isinstance(capture_timestamp, datetime):
        return capture_timestamp.date().isoformat()
    try:
        parsed = datetime.fromisoformat(capture_timestamp)
    except ValueError:
        return datetime.now().astimezone().date().isoformat()
    return parsed.date().isoformat()


def _ledger_database_path() -> str:
    raw_path = os.getenv(_LEDGER_DB_ENV_VAR, "").strip()
    resolved_path = raw_path if raw_path else str(_DEFAULT_LEDGER_DB_PATH)
    initialize_sqlite_ledger(resolved_path)
    return resolved_path


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
