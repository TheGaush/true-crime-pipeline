"""Offline proof that the repo-wide zero-spend guard is installed."""

import os
import socket

import pytest

import conftest


def test_session_starts_with_provider_keys_removed():
    assert "GEMINI_API_KEY" not in os.environ
    assert "DEEPSEEK_API_KEY" not in os.environ
    assert "ELEVENLABS_API_KEY" not in os.environ


def test_live_sandbox_requires_both_gates():
    assert conftest.live_authorized(True, "1") is True
    assert conftest.live_authorized(True, None) is False
    assert conftest.live_authorized(False, "1") is False
    assert conftest.live_authorized(True, "0") is False


def test_scrub_removes_provider_keys():
    env = {"GEMINI_API_KEY": "present", "PATH": "/usr/bin"}
    conftest.scrub_provider_env(env)
    assert "GEMINI_API_KEY" not in env
    assert env["PATH"] == "/usr/bin"


def test_outbound_tcp_is_blocked():
    sock = socket.socket()
    try:
        with pytest.raises(OSError, match="blocked outbound socket"):
            sock.connect(("203.0.113.5", 443))
    finally:
        sock.close()


def test_outbound_dns_is_blocked():
    with pytest.raises(OSError, match="blocked outbound DNS"):
        socket.getaddrinfo("example.com", 443)


def test_loopback_connect_is_allowed():
    server = socket.socket()
    client = socket.socket()
    try:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        client.connect(("127.0.0.1", port))
    finally:
        client.close()
        server.close()
