"""Loopback desk API. Mutating calls require the local token."""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response

from desk_api.db_service import audit, claim, connect, contained, require_sqlite

MAX_UPLOAD = 250 * 1024 * 1024


def create_app(db_path: str, upload_root: str, token_path: str, ui_port: int = 5173, check_sqlite: bool = True) -> FastAPI:
    if check_sqlite:
        require_sqlite()
    token = secrets.token_hex(32)
    path = Path(token_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token + "\n", encoding="utf8")
    os.chmod(path, 0o600)
    connection = connect(db_path)
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[f"http://127.0.0.1:{ui_port}", f"http://localhost:{ui_port}"],
        allow_methods=["GET", "POST"],
        allow_headers=["X-Local-Auth-Token"],
    )

    def authorize(header: str | None) -> None:
        if header != token:
            raise HTTPException(status_code=401, detail="local token required")

    @app.get("/api/conveyor")
    def conveyor() -> dict:
        rows = connection.execute("SELECT episode_id, scene_id, status FROM cards ORDER BY episode_id").fetchall()
        return {"cards": [dict(row) for row in rows]}

    @app.get("/api/accounts")
    def accounts() -> dict:
        return {"accounts": [{"account_id": "tab-1"}, {"account_id": "tab-2"}, {"account_id": "tab-3"}]}

    @app.post("/api/episodes/{episode_id}/cards")
    def cards(episode_id: str, body: dict, x_local_auth_token: str | None = Header(default=None)) -> dict:
        authorize(x_local_auth_token)
        if not claim(connection, episode_id, body["scene_id"]):
            raise HTTPException(status_code=409, detail="card already claimed")
        return {"episode_id": episode_id, "scene_id": body["scene_id"], "status": "CLAIMED"}

    @app.post("/api/episodes/{episode_id}/drop")
    async def drop(episode_id: str, x_local_auth_token: str | None = Header(default=None), content_type: str | None = Header(default=None)) -> dict:
        authorize(x_local_auth_token)
        if content_type and "video" not in content_type and "octet-stream" not in content_type:
            raise HTTPException(status_code=415, detail="video required")
        audit(connection, "DROP", episode_id)
        return {"accepted": True}

    @app.get("/api/episodes/{episode_id}/animatic")
    def animatic(episode_id: str, range: str | None = Header(default=None)) -> Response:
        file_path = Path(upload_root) / episode_id / "animatic.mp4"
        if not contained(upload_root, str(file_path)) or not file_path.is_file():
            raise HTTPException(status_code=404, detail="missing animatic")
        if range:
            return Response(content=file_path.read_bytes()[:16], status_code=206, headers={"Accept-Ranges": "bytes", "Content-Range": "bytes 0-15/*"})
        return FileResponse(file_path)

    @app.post("/api/episodes/{episode_id}/approvals")
    def approvals(episode_id: str, body: dict, x_local_auth_token: str | None = Header(default=None)) -> dict:
        authorize(x_local_auth_token)
        audit(connection, "APPROVAL", f"{episode_id}:{body['gate']}:{body['reviewer_id']}")
        return {"recorded": True}

    @app.post("/api/config/backend")
    def backend(body: dict, x_local_auth_token: str | None = Header(default=None)) -> dict:
        authorize(x_local_auth_token)
        audit(connection, "CONFIG", body.get("adapter", "primary"))
        return {"ok": True}

    @app.websocket("/ws/events")
    async def events(socket: WebSocket) -> None:
        if socket.headers.get("x-local-auth-token") != token:
            await socket.close(code=1008)
            return
        await socket.accept()
        await socket.send_json({"type": "ready"})
        try:
            await socket.receive_text()
        except WebSocketDisconnect:
            return

    app.state.token = token
    app.state.connection = connection
    return app


def bind_host(host: str) -> str:
    if host == "0.0.0.0":
        raise RuntimeError("refusing a public bind")
    return "127.0.0.1"
