import sqlite3
import sys
from pathlib import Path

from fastapi.testclient import TestClient

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))
from desk_api.db_service import require_sqlite
from desk_api.server import bind_host, create_app


def test_sqlite_gate_and_local_api(tmp_path: Path):
    require_sqlite((3, 51, 3))
    try:
        require_sqlite((3, 45, 1))
        assert False
    except Exception as error:
        assert "older" in str(error)
    try:
        bind_host("0.0.0.0")
        assert False
    except RuntimeError:
        pass
    assert bind_host("127.0.0.1") == "127.0.0.1"
    app = create_app(str(tmp_path / "pipeline.db"), str(tmp_path), str(tmp_path / "token"), check_sqlite=False)
    client = TestClient(app)
    denied = client.post("/api/episodes/ep/cards", json={"scene_id": "s1"})
    assert denied.status_code == 401
    headers = {"X-Local-Auth-Token": app.state.token}
    assert client.post("/api/episodes/ep/cards", json={"scene_id": "s1"}, headers=headers).status_code == 200
    conflict = client.post("/api/episodes/ep/cards", json={"scene_id": "s1"}, headers=headers)
    assert conflict.status_code == 409
    bad = client.post("/api/episodes/ep/drop", headers={**headers, "Content-Type": "text/plain"})
    assert bad.status_code == 415
    clip = tmp_path / "ep"
    clip.mkdir()
    (clip / "animatic.mp4").write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 32)
    ranged = client.get("/api/episodes/ep/animatic", headers={"Range": "bytes=0-15"})
    assert ranged.status_code == 206
    outside = tmp_path / "token"
    assert outside.stat().st_mode & 0o777 == 0o600
    assert client.post("/api/episodes/ep/approvals", json={"gate": "FACTUAL_ACCURACY", "reviewer_id": "ada"}, headers=headers).status_code == 200
    rows = app.state.connection.execute("SELECT action FROM audit_log").fetchall()
    assert any(row["action"] == "APPROVAL" for row in rows)
    with client.websocket_connect("/ws/events", headers=headers) as socket:
        assert socket.receive_json()["type"] == "ready"
    assert sqlite3.sqlite_version_info >= (3, 45, 0)
