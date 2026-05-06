from __future__ import annotations

from services.api import local_server


def test_main_accepts_documented_host_and_port(monkeypatch) -> None:
    observed: dict[str, int | str] = {}

    def fake_run_server(host: str, port: int, *, stderr=None) -> int:
        del stderr
        observed["host"] = host
        observed["port"] = port
        return 0

    monkeypatch.setattr(local_server, "run_server", fake_run_server)

    exit_code = local_server.main(["--host", "0.0.0.0", "--port", "8765"])

    assert exit_code == 0
    assert observed == {"host": "0.0.0.0", "port": 8765}
