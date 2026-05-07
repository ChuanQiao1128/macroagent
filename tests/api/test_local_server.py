from __future__ import annotations

import json
from email.message import Message
from io import BytesIO
from typing import Any

from services.api.local_server import LocalAnalyzePhotoHandler

_ANALYZE_PATH = "/v1/meals/analyze-photo"


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
