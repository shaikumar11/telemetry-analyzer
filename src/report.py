"""
report.py
Turns an AnalysisResult + raw samples into (1) a human-readable text report with
optimization suggestions, and (2) a PNG chart of CPU/memory over time with
anomalies marked.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
from datetime import datetime

from collector import DB_PATH
from analyzer import load_samples, analyze

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"


def suggest_optimizations(result) -> list:
    suggestions = []
    if result.max_cpu >= 80:
        suggestions.append(
            "Sustained high CPU detected — investigate the top-offending process for "
            "busy-polling loops or missing backoff/sleep in hot paths."
        )
    if result.max_mem >= 85:
        suggestions.append(
            "Memory usage approached capacity — check for unbounded caches, growing "
            "collections, or unreleased handles in long-running processes."
        )
    disk_spikes = [a for a in result.anomalies if a.kind == "spike_disk"]
    if disk_spikes:
        suggestions.append(
            f"{len(disk_spikes)} disk I/O spike(s) detected — consider batching writes "
            "or checking for unexpected background sync/indexing activity."
        )
    net_spikes = [a for a in result.anomalies if a.kind == "spike_net"]
    if net_spikes:
        suggestions.append(
            f"{len(net_spikes)} network I/O spike(s) detected — check for unthrottled "
            "background sync, telemetry uploads, or update checks."
        )
    if not suggestions:
        suggestions.append("No sustained pressure or spikes detected in this window — system fundamentals look healthy.")
    return suggestions


def text_report(result) -> str:
    lines = []
    lines.append("=" * 60)
    lines.append("SYSTEM TELEMETRY & PERFORMANCE REPORT")
    lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("=" * 60)
    lines.append(f"Samples analyzed : {result.sample_count}")
    lines.append(f"Avg CPU / Max CPU: {result.avg_cpu:.1f}% / {result.max_cpu:.1f}%")
    lines.append(f"Avg Mem / Max Mem: {result.avg_mem:.1f}% / {result.max_mem:.1f}%")
    lines.append("")
    lines.append(f"Anomalies detected: {len(result.anomalies)}")
    for a in result.anomalies:
        lines.append(f"  - [{a.kind}] {a.detail}")
    lines.append("")
    lines.append("Top CPU-consuming processes (by # samples as top process):")
    for name, count in result.top_offenders:
        lines.append(f"  - {name}: {count} samples")
    lines.append("")
    lines.append("Suggested optimizations:")
    for s in suggest_optimizations(result):
        lines.append(f"  * {s}")
    lines.append("=" * 60)
    return "\n".join(lines)


def chart(rows, result, out_path: Path):
    ts = list(range(len(rows)))
    cpu = [r["cpu_percent"] for r in rows]
    mem = [r["mem_percent"] for r in rows]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(ts, cpu, label="CPU %", color="#1F4E79")
    ax.plot(ts, mem, label="Memory %", color="#C0504D")

    anomaly_x = [i for i, r in enumerate(rows) if r["ts"] in {a.ts for a in result.anomalies}]
    if anomaly_x:
        ax.scatter(anomaly_x, [cpu[i] for i in anomaly_x], color="red", zorder=5, label="Anomaly")

    ax.set_xlabel("Sample #")
    ax.set_ylabel("Percent")
    ax.set_title("System Telemetry Over Time")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def generate(db_path: Path = DB_PATH):
    rows = load_samples(db_path)
    result = analyze(rows)
    report_txt = text_report(result)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    txt_path = REPORTS_DIR / "report.txt"
    txt_path.write_text(report_txt)

    png_path = REPORTS_DIR / "telemetry_chart.png"
    if rows:
        chart(rows, result, png_path)

    return report_txt, txt_path, png_path


if __name__ == "__main__":
    report_txt, txt_path, png_path = generate()
    print(report_txt)
    print(f"\nSaved report to {txt_path}")
    print(f"Saved chart to {png_path}")
