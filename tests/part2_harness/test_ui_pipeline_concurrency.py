"""Fifty short writes on one WAL database."""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path


def test_fifty_writes_do_not_lock(tmp_path: Path):
    path = tmp_path / "pipeline.db"
    setup = sqlite3.connect(path)
    setup.execute("PRAGMA journal_mode=WAL")
    setup.execute("PRAGMA busy_timeout=5000")
    setup.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, n INTEGER)")
    setup.commit()
    setup.close()
    errors: list[str] = []
    times: list[float] = []
    gate = threading.Barrier(50)

    def write(index: int) -> None:
        connection = sqlite3.connect(path, timeout=5)
        connection.execute("PRAGMA busy_timeout=5000")
        gate.wait()
        try:
            connection.execute("BEGIN IMMEDIATE")
            started = time.perf_counter()
            connection.execute("INSERT INTO events (n) VALUES (?)", (index,))
            connection.execute("COMMIT")
        except sqlite3.OperationalError as error:
            errors.append(str(error))
        else:
            times.append((time.perf_counter() - started) * 1000)
        connection.close()

    threads = [threading.Thread(target=write, args=(index,)) for index in range(50)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    ordered = sorted(times)
    p99 = ordered[int(len(ordered) * 0.99) - 1]
    assert p99 < 25
    count = sqlite3.connect(path).execute("SELECT COUNT(*) FROM events").fetchone()[0]
    assert count == 50
