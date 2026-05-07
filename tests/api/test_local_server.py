from __future__ import annotations

import json
from email.message import Message
from io import BytesIO
from pathlib import Path
from typing import Any

from services.api.local_server import LocalAnalyzePhotoHandler
from services.storage import insert_user_nutrition_ledger_entry

_ANALYZE_PATH = "/v1/meals/analyze-photo"
_USER_HISTORY_PATH = "/v1/users/history"
_USER_DAILY_TOTALS_PATH = "/v1/users/daily-totals"
_USER_HEALTHKIT_EXPORT_PREP_PATH = "/v1/users/healthkit-export-prep"
_LEDGER_DB_ENV_VAR = "MACROAGENT_LEDGER_DB_PATH"


def _raw_request_payload(request_id: str) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "user_id": "user_tester",
        "image_identity": {
            "image_sha256": "a" * 64,
            "image_format": "heic",
            "width_px": 3024,
            "height_px": 4032,
            "byte_size": 2456789,
        },
        "capture_metadata": {
            "device_model": "iPhone15,3",
            "os_version": "iOS 18.1",
            "camera_position": "back",
            "orientation": "portrait",
            "pitch_degrees": 2.5,
            "roll_degrees": -1.0,
            "focal_length_mm": 5.7,
            "lens_hint": "wide",
            "depth_available": True,
            "depth_quality": "high",
            "lidar_available": True,
            "barcode_payload": "0123456789012",
            "ocr_text_snippets": ["2 tbsp olive oil", "chicken breast"],
            "reference_object_hint": "standard dinner plate",
            "capture_timestamp": "2026-05-01T12:34:56+00:00",
        },
    }


class _HandlerHarness(LocalAnalyzePhotoHandler):
    def __init__(
        self,
        *,
        method: str,
        path: str,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.path = path
        self.command = method
        self.rfile = BytesIO(body if body is not None else b"")
        self.wfile = BytesIO()
        self.headers = Message()
        for key, value in (headers or {}).items():
            self.headers[key] = value
        self.status_code: int | None = None
        self.response_headers: dict[str, str] = {}

    def send_response(self, code: int, message: str | None = None) -> None:
        del message
        self.status_code = code

    def send_header(self, keyword: str, value: str) -> None:
        self.response_headers[keyword] = value

    def end_headers(self) -> None:
        return


def _invoke(
    *,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    raw_body: bytes | None = None,
) -> tuple[int, dict[str, str], dict[str, Any]]:
    body = raw_body
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    headers: dict[str, str] = {}
    if body is not None:
        headers["Content-Type"] = "application/json"
        headers["Content-Length"] = str(len(body))

    handler = _HandlerHarness(method=method, path=path, body=body, headers=headers)
    getattr(handler, f"do_{method}")()

    response_body = handler.wfile.getvalue().decode("utf-8")
    json_payload = json.loads(response_body) if response_body else {}
    assert handler.status_code is not None
    return handler.status_code, handler.response_headers, json_payload


def _collect_keys(payload: Any) -> set[str]:
    if isinstance(payload, dict):
        keys = set(payload.keys())
        for value in payload.values():
            keys.update(_collect_keys(value))
        return keys
    if isinstance(payload, list):
        keys: set[str] = set()
        for item in payload:
            keys.update(_collect_keys(item))
        return keys
    return set()


def _seed_user_history_rows(db_path: Path) -> None:
    accepted_entry_id = insert_user_nutrition_ledger_entry(
        db_path,
        user_id="user-a",
        meal_id="meal-a",
        entry_kind="accepted",
        source="deterministic",
        local_date="2026-05-04",
        created_at="2026-05-04T08:00:00+12:00",
        entry_id="entry-a-accepted",
        kcal=400.0,
        protein_g=20.0,
        carbs_g=40.0,
        fat_g=10.0,
        sugar_g=5.0,
        sodium_mg=300.0,
        fiber_g=4.0,
    )
    insert_user_nutrition_ledger_entry(
        db_path,
        user_id="user-a",
        meal_id="meal-a",
        entry_kind="corrected",
        source="deterministic",
        supersedes_entry_id=accepted_entry_id,
        local_date="2026-05-04",
        created_at="2026-05-04T08:10:00+12:00",
        entry_id="entry-a-corrected",
        kcal=500.0,
        protein_g=25.0,
        carbs_g=55.0,
        fat_g=15.0,
        sugar_g=8.0,
        sodium_mg=350.0,
        fiber_g=6.0,
    )
    insert_user_nutrition_ledger_entry(
        db_path,
        user_id="user-a",
        meal_id="meal-b",
        entry_kind="accepted",
        source="deterministic",
        local_date="2026-05-04",
        created_at="2026-05-04T09:00:00+12:00",
        entry_id="entry-b-accepted",
        kcal=250.0,
        protein_g=10.0,
        carbs_g=30.0,
        fat_g=8.0,
        sugar_g=12.0,
        sodium_mg=150.0,
        fiber_g=3.0,
    )
    insert_user_nutrition_ledger_entry(
        db_path,
        user_id="user-a",
        meal_id="meal-manual",
        entry_kind="accepted",
        source="manual_entry",
        local_date="2026-05-04",
        created_at="2026-05-04T09:10:00+12:00",
        entry_id="entry-manual",
        kcal=999.0,
    )
    insert_user_nutrition_ledger_entry(
        db_path,
        user_id="user-b",
        meal_id="meal-other-user",
        entry_kind="accepted",
        source="deterministic",
        local_date="2026-05-04",
        created_at="2026-05-04T09:20:00+12:00",
        entry_id="entry-other-user",
        kcal=777.0,
    )
    insert_user_nutrition_ledger_entry(
        db_path,
        user_id="user-a",
        meal_id="meal-other-day",
        entry_kind="accepted",
        source="deterministic",
        local_date="2026-05-05",
        created_at="2026-05-05T08:00:00+12:00",
        entry_id="entry-other-day",
        kcal=888.0,
    )


def test_health_returns_ok() -> None:
    status, headers, payload = _invoke(method="GET", path="/health")

    assert status == 200
    assert headers["Content-Type"].startswith("application/json")
    assert payload == {"status": "ok"}


def test_analyze_photo_accepts_raw_photo_request() -> None:
    request_id = "req_accept_local_http"

    status, headers, payload = _invoke(
        method="POST",
        path=_ANALYZE_PATH,
        payload=_raw_request_payload(request_id),
    )

    assert status == 200
    assert headers["Content-Type"].startswith("application/json")
    assert payload["request_id"] == request_id
    assert payload["trace_id"] == f"trace:{request_id}"
    assert payload["status"] in {"ACCEPT", "WARN", "CLARIFY", "BLOCK"}
    assert "quick_corrections" in payload
    assert "nutrition" in payload or payload["status"] == "BLOCK"
    if payload["status"] == "BLOCK":
        assert payload["reasons"]
    else:
        assert payload["nutrition"] is not None
        assert 1 <= len(payload["quick_corrections"]) <= 4

    forbidden_keys = {
        "image",
        "image_bytes",
        "raw_image",
        "raw_bytes",
        "base64_image",
        "image_base64",
        "path",
        "image_path",
        "local_image_path",
    }
    assert forbidden_keys.isdisjoint(_collect_keys(payload))


def test_analyze_photo_accepts_facade_request_shape() -> None:
    request_id = "req_warn_local_http"
    facade_payload = {
        "payload": _raw_request_payload(request_id),
        "options": {"log_anyway": False},
    }

    status, _, payload = _invoke(
        method="POST",
        path=_ANALYZE_PATH,
        payload=facade_payload,
    )

    assert status == 200
    assert payload["request_id"] == request_id
    assert payload["status"] == "WARN"
    assert payload["trace_id"] == f"trace:{request_id}"
    assert payload["quick_corrections"]


def test_invalid_json_returns_structured_error() -> None:
    status, _, payload = _invoke(
        method="POST",
        path=_ANALYZE_PATH,
        raw_body=b'{"payload":',
    )

    assert status == 400
    assert payload["error"]["code"] == "invalid_json"
    assert payload["error"]["message"] == "request body must be valid JSON"
    assert {"line", "column", "position"} <= set(payload["error"]["details"])


def test_invalid_schema_returns_structured_error() -> None:
    invalid_payload = {"payload": {"request_id": "req_invalid_schema"}}

    status, _, payload = _invoke(
        method="POST",
        path=_ANALYZE_PATH,
        payload=invalid_payload,
    )

    assert status == 400
    assert payload["error"]["code"] == "invalid_schema"
    assert payload["error"]["message"] == (
        "request body does not match AnalyzePhotoFacadeRequest"
    )
    assert isinstance(payload["error"]["details"], list)
    assert payload["error"]["details"]


def test_unsupported_path_returns_structured_error() -> None:
    status, _, payload = _invoke(method="GET", path="/v1/does-not-exist")

    assert status == 404
    assert payload["error"]["code"] == "unsupported_path"
    assert "not supported" in payload["error"]["message"]


def test_unsupported_method_returns_structured_error() -> None:
    status, headers, payload = _invoke(method="GET", path=_ANALYZE_PATH)

    assert status == 405
    assert headers["Allow"] == "POST"
    assert payload["error"]["code"] == "unsupported_method"
    assert "not supported for this path" in payload["error"]["message"]
    assert payload["error"]["details"] == {"allowed_methods": ["POST"]}


def test_get_user_history_endpoint_filters_by_user_day_and_include_inactive(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    db_path = tmp_path / "local_server.sqlite3"
    monkeypatch.setenv(_LEDGER_DB_ENV_VAR, str(db_path))
    _seed_user_history_rows(db_path)

    status, _, payload = _invoke(
        method="GET",
        path=(
            f"{_USER_HISTORY_PATH}"
            "?user_id=user-a&local_date=2026-05-04&include_inactive=true&limit=10"
        ),
    )

    assert status == 200
    assert payload["user_id"] == "user-a"
    assert payload["local_date"] == "2026-05-04"
    assert payload["include_inactive"] is True
    assert payload["limit"] == 10
    assert payload["entry_count"] == 4

    entry_ids = tuple(entry["entry_id"] for entry in payload["entries"])
    assert entry_ids == (
        "entry-manual",
        "entry-b-accepted",
        "entry-a-corrected",
        "entry-a-accepted",
    )
    by_entry_id = {entry["entry_id"]: entry for entry in payload["entries"]}
    assert by_entry_id["entry-a-corrected"]["active"] is True
    assert by_entry_id["entry-a-corrected"]["supersedes_entry_id"] == "entry-a-accepted"
    assert by_entry_id["entry-a-accepted"]["active"] is False

    missing_user_status, _, missing_user_payload = _invoke(
        method="GET",
        path=f"{_USER_HISTORY_PATH}?local_date=2026-05-04",
    )
    assert missing_user_status == 400
    assert missing_user_payload["error"]["code"] == "invalid_schema"
    assert missing_user_payload["error"]["message"] == (
        "missing required query parameter 'user_id'"
    )


def test_get_daily_totals_and_healthkit_export_prep_endpoints_use_active_deterministic_rows_only(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    db_path = tmp_path / "local_server.sqlite3"
    monkeypatch.setenv(_LEDGER_DB_ENV_VAR, str(db_path))
    _seed_user_history_rows(db_path)

    totals_status, _, totals_payload = _invoke(
        method="GET",
        path=f"{_USER_DAILY_TOTALS_PATH}?user_id=user-a&local_date=2026-05-04",
    )
    assert totals_status == 200
    assert totals_payload == {
        "user_id": "user-a",
        "local_date": "2026-05-04",
        "meal_count": 2,
        "active_entry_count": 2,
        "kcal": 750.0,
        "protein_g": 35.0,
        "carbs_g": 85.0,
        "fat_g": 23.0,
        "sugar_g": 20.0,
        "sodium_mg": 500.0,
        "fiber_g": 9.0,
    }

    prep_status, _, prep_payload = _invoke(
        method="GET",
        path=f"{_USER_HEALTHKIT_EXPORT_PREP_PATH}?user_id=user-a&local_date=2026-05-04",
    )
    assert prep_status == 200
    assert prep_payload["user_id"] == "user-a"
    assert prep_payload["local_date"] == "2026-05-04"
    assert prep_payload["entry_count"] == 2
    assert tuple(entry["entry_id"] for entry in prep_payload["entries"]) == (
        "entry-a-corrected",
        "entry-b-accepted",
    )

    for entry in prep_payload["entries"]:
        assert len(entry["quantities"]) == 7
        for quantity in entry["quantities"]:
            assert quantity["status"] == "ready"
            assert quantity["value"] is not None
            assert quantity["skip_reason"] is None
