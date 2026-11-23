"""Repo-wide pytest zero-spend guard (Task 001, F-01).

Ordinary runs strip provider API keys and block outbound DNS/TCP.
Loopback (127.0.0.1, ::1, localhost) stays open for local servers.
Paid sockets stay closed unless both ``--live-sandbox`` and
``ALLOW_PAID_SANDBOX=1`` are set. That pair is the Task 200 opt-in.
"""

from __future__ import annotations

import os
import socket

import pytest

PROVIDER_ENV_KEYS = (
    "GEMINI_API_KEY",
    "DEEPSEEK_API_KEY",
    "ELEVENLABS_API_KEY",
    "GOOGLE_API_KEY",
    "GOOGLE_GENAI_API_KEY",
    "VERTEX_API_KEY",
    "VERTEXAI_API_KEY",
    "OPENAI_API_KEY",
)

_LOOPBACK = frozenset({None, "", "127.0.0.1", "::1", "localhost"})
_INSTALLED = False


class ZeroSpendSocketBlocked(OSError):
    """Raised when a test opens a non-loopback socket."""


def live_authorized(live_flag: bool, allow_value: str | None) -> bool:
    return bool(live_flag) and allow_value == "1"


def scrub_provider_env(environ: dict[str, str] | None = None) -> None:
    env = os.environ if environ is None else environ
    for key in list(env):
        if key in PROVIDER_ENV_KEYS or key.endswith("_API_KEY") or key.endswith("_SECRET"):
            env.pop(key, None)


def _host_of(address: object) -> str | None:
    if isinstance(address, tuple) and address:
        host = address[0]
    elif isinstance(address, str):
        host = address
    else:
        return None
    if isinstance(host, bytes):
        return host.decode("utf-8", "replace")
    return str(host) if host is not None else None


def _guard(sock: socket.socket, address: object) -> None:
    if getattr(sock, "family", None) == socket.AF_UNIX:
        return
    host = _host_of(address)
    if host in _LOOPBACK:
        return
    raise ZeroSpendSocketBlocked(
        f"zero-spend offline guard blocked outbound socket to {host}"
    )


def install_socket_block() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_create = socket.create_connection
    real_getaddrinfo = socket.getaddrinfo

    def connect(self: socket.socket, address: object) -> None:
        _guard(self, address)
        return real_connect(self, address)

    def connect_ex(self: socket.socket, address: object) -> int:
        _guard(self, address)
        return real_connect_ex(self, address)

    def create_connection(address: object, *args: object, **kwargs: object) -> socket.socket:
        host = _host_of(address)
        if host not in _LOOPBACK:
            raise ZeroSpendSocketBlocked(
                f"zero-spend offline guard blocked outbound socket to {host}"
            )
        return real_create(address, *args, **kwargs)

    def getaddrinfo(host: object, port: object, *args: object, **kwargs: object) -> list:
        text = host.decode("utf-8", "replace") if isinstance(host, bytes) else host
        if text not in _LOOPBACK:
            raise ZeroSpendSocketBlocked(
                f"zero-spend offline guard blocked outbound DNS for {text}"
            )
        return real_getaddrinfo(host, port, *args, **kwargs)

    socket.socket.connect = connect  # type: ignore[method-assign]
    socket.socket.connect_ex = connect_ex  # type: ignore[method-assign]
    socket.create_connection = create_connection  # type: ignore[assignment]
    socket.getaddrinfo = getaddrinfo  # type: ignore[assignment]


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--disable-socket",
        action="store_true",
        help="Block outbound sockets except loopback (default for ordinary runs).",
    )
    parser.addoption(
        "--live-sandbox",
        action="store_true",
        help="With ALLOW_PAID_SANDBOX=1, allow paid provider sockets (Task 200 only).",
    )


def pytest_configure(config: pytest.Config) -> None:
    if live_authorized(config.getoption("--live-sandbox"), os.environ.get("ALLOW_PAID_SANDBOX")):
        return
    scrub_provider_env()
    install_socket_block()
