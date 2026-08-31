"""
collector.py
Polls system-level telemetry (CPU, memory, disk I/O, network I/O, top processes)
at a fixed interval using psutil, and persists each sample to a SQLite database.

psutil is cross-platform (Windows/Linux/macOS) — the same collector runs unmodified
on a Windows device (uses the same public API surface: psutil.cpu_percent,
psutil.virtual_memory, psutil.disk_io_counters, psutil.net_io_counters,
psutil.process_iter).
"""
import sqlite3
import time
import psutil
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "telemetry.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    cpu_percent REAL NOT NULL,
    mem_percent REAL NOT NULL,
    mem_used_mb REAL NOT NULL,
    disk_read_mb REAL NOT NULL,
    disk_write_mb REAL NOT NULL,
    net_sent_mb REAL NOT NULL,
    net_recv_mb REAL NOT NULL,
    top_process TEXT,
    top_process_cpu REAL
);
"""


def init_db(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(SCHEMA)
    conn.commit()
    return conn


def _top_process():
    """Return (name, cpu_percent) of the highest CPU-consuming process in this sample."""
    best_name, best_cpu = None, -1.0
    for p in psutil.process_iter(["name", "cpu_percent"]):
        try:
            cpu = p.info["cpu_percent"] or 0.0
            if cpu > best_cpu:
                best_cpu, best_name = cpu, p.info["name"]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return best_name, best_cpu


def sample_once(prev_disk=None, prev_net=None):
    """Take one telemetry sample. Returns (row_dict, disk_counters, net_counters)."""
    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()

    disk = psutil.disk_io_counters()
    net = psutil.net_io_counters()

    if prev_disk is not None:
        read_mb = max(0.0, (disk.read_bytes - prev_disk.read_bytes) / (1024 * 1024))
        write_mb = max(0.0, (disk.write_bytes - prev_disk.write_bytes) / (1024 * 1024))
    else:
        read_mb = write_mb = 0.0

    if prev_net is not None:
        sent_mb = max(0.0, (net.bytes_sent - prev_net.bytes_sent) / (1024 * 1024))
        recv_mb = max(0.0, (net.bytes_recv - prev_net.bytes_recv) / (1024 * 1024))
    else:
        sent_mb = recv_mb = 0.0

    top_name, top_cpu = _top_process()

    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "cpu_percent": cpu,
        "mem_percent": mem.percent,
        "mem_used_mb": mem.used / (1024 * 1024),
        "disk_read_mb": read_mb,
        "disk_write_mb": write_mb,
        "net_sent_mb": sent_mb,
        "net_recv_mb": recv_mb,
        "top_process": top_name,
        "top_process_cpu": top_cpu,
    }
    return row, disk, net


def insert_row(conn: sqlite3.Connection, row: dict):
    conn.execute(
        """INSERT INTO samples
           (ts, cpu_percent, mem_percent, mem_used_mb, disk_read_mb, disk_write_mb,
            net_sent_mb, net_recv_mb, top_process, top_process_cpu)
           VALUES (:ts, :cpu_percent, :mem_percent, :mem_used_mb, :disk_read_mb,
                   :disk_write_mb, :net_sent_mb, :net_recv_mb, :top_process, :top_process_cpu)""",
        row,
    )
    conn.commit()


def run_collector(duration_sec: int, interval_sec: float = 2.0, db_path: Path = DB_PATH):
    conn = init_db(db_path)
    prev_disk = psutil.disk_io_counters()
    prev_net = psutil.net_io_counters()
    start = time.time()
    n = 0
    while time.time() - start < duration_sec:
        row, prev_disk, prev_net = sample_once(prev_disk, prev_net)
        insert_row(conn, row)
        n += 1
        time.sleep(max(0.0, interval_sec - 0.5))  # cpu_percent already blocks 0.5s
    conn.close()
    return n


if __name__ == "__main__":
    import sys
    dur = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    count = run_collector(dur)
    print(f"Collected {count} samples into {DB_PATH}")
