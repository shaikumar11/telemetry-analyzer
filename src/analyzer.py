"""
analyzer.py
Reads telemetry samples from SQLite and flags anomalies using two complementary
rules, chosen because single-point thresholds alone produce noisy false positives:

1. Sustained-high-usage rule: CPU or memory stays above a threshold for N
   consecutive samples in a row (catches real pressure, not momentary blips).
2. Statistical spike rule: a sample's metric is more than K standard deviations
   above the trailing mean (catches sudden anomalous jumps, e.g. disk I/O spikes).
"""
import sqlite3
import statistics
from dataclasses import dataclass, field
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "telemetry.db"

CPU_SUSTAINED_THRESHOLD = 80.0
MEM_SUSTAINED_THRESHOLD = 85.0
SUSTAINED_MIN_SAMPLES = 3
SPIKE_STD_MULTIPLIER = 2.5
ROLLING_WINDOW = 10


@dataclass
class Anomaly:
    ts: str
    kind: str          # "sustained_cpu" | "sustained_mem" | "spike_disk" | "spike_net"
    metric_value: float
    detail: str


@dataclass
class AnalysisResult:
    sample_count: int
    avg_cpu: float
    avg_mem: float
    max_cpu: float
    max_mem: float
    anomalies: list = field(default_factory=list)
    top_offenders: list = field(default_factory=list)  # [(process_name, times_seen_as_top)]


def load_samples(db_path: Path = DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM samples ORDER BY id ASC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _sustained_runs(values, threshold, min_len):
    """Return indices where a run of >= min_len consecutive values exceeds threshold."""
    flagged = []
    run_start = None
    for i, v in enumerate(values):
        if v >= threshold:
            if run_start is None:
                run_start = i
        else:
            if run_start is not None and i - run_start >= min_len:
                flagged.append((run_start, i - 1))
            run_start = None
    if run_start is not None and len(values) - run_start >= min_len:
        flagged.append((run_start, len(values) - 1))
    return flagged


def _rolling_spikes(values, window, std_multiplier):
    flagged = []
    for i in range(window, len(values)):
        window_vals = values[i - window:i]
        mean = statistics.mean(window_vals)
        stdev = statistics.pstdev(window_vals) or 0.01
        if values[i] - mean > std_multiplier * stdev:
            flagged.append(i)
    return flagged


def analyze(rows: list) -> AnalysisResult:
    if not rows:
        return AnalysisResult(0, 0.0, 0.0, 0.0, 0.0)

    cpu = [r["cpu_percent"] for r in rows]
    mem = [r["mem_percent"] for r in rows]
    disk_rw = [r["disk_read_mb"] + r["disk_write_mb"] for r in rows]
    net_io = [r["net_sent_mb"] + r["net_recv_mb"] for r in rows]

    anomalies = []

    for start, end in _sustained_runs(cpu, CPU_SUSTAINED_THRESHOLD, SUSTAINED_MIN_SAMPLES):
        anomalies.append(Anomaly(
            ts=rows[start]["ts"], kind="sustained_cpu",
            metric_value=max(cpu[start:end + 1]),
            detail=f"CPU >= {CPU_SUSTAINED_THRESHOLD}% for {end - start + 1} consecutive samples "
                   f"({rows[start]['ts']} to {rows[end]['ts']})",
        ))

    for start, end in _sustained_runs(mem, MEM_SUSTAINED_THRESHOLD, SUSTAINED_MIN_SAMPLES):
        anomalies.append(Anomaly(
            ts=rows[start]["ts"], kind="sustained_mem",
            metric_value=max(mem[start:end + 1]),
            detail=f"Memory >= {MEM_SUSTAINED_THRESHOLD}% for {end - start + 1} consecutive samples "
                   f"({rows[start]['ts']} to {rows[end]['ts']})",
        ))

    for i in _rolling_spikes(disk_rw, ROLLING_WINDOW, SPIKE_STD_MULTIPLIER):
        anomalies.append(Anomaly(
            ts=rows[i]["ts"], kind="spike_disk", metric_value=disk_rw[i],
            detail=f"Disk I/O spike: {disk_rw[i]:.2f} MB vs trailing {ROLLING_WINDOW}-sample average",
        ))

    for i in _rolling_spikes(net_io, ROLLING_WINDOW, SPIKE_STD_MULTIPLIER):
        anomalies.append(Anomaly(
            ts=rows[i]["ts"], kind="spike_net", metric_value=net_io[i],
            detail=f"Network I/O spike: {net_io[i]:.2f} MB vs trailing {ROLLING_WINDOW}-sample average",
        ))

    offenders = {}
    for r in rows:
        if r["top_process"]:
            offenders[r["top_process"]] = offenders.get(r["top_process"], 0) + 1
    top_offenders = sorted(offenders.items(), key=lambda kv: kv[1], reverse=True)[:5]

    return AnalysisResult(
        sample_count=len(rows),
        avg_cpu=statistics.mean(cpu),
        avg_mem=statistics.mean(mem),
        max_cpu=max(cpu),
        max_mem=max(mem),
        anomalies=anomalies,
        top_offenders=top_offenders,
    )


if __name__ == "__main__":
    rows = load_samples()
    result = analyze(rows)
    print(f"Samples: {result.sample_count}")
    print(f"Avg CPU: {result.avg_cpu:.1f}%  Max CPU: {result.max_cpu:.1f}%")
    print(f"Avg Mem: {result.avg_mem:.1f}%  Max Mem: {result.max_mem:.1f}%")
    print(f"Anomalies found: {len(result.anomalies)}")
    for a in result.anomalies:
        print(f"  [{a.kind}] {a.detail}")
