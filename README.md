# System Telemetry & Performance Analyzer

A small tool that collects live system telemetry (CPU, memory, disk I/O, network I/O,
top CPU-consuming process), stores it in SQLite, detects anomalies, and generates a
performance report with a chart — the same kind of workflow used to understand device
behavior and find optimization opportunities.

Built with [psutil](https://github.com/giampaolo/psutil), which is cross-platform:
the collector runs unmodified on Windows, Linux, or macOS since it only uses psutil's
public API (`cpu_percent`, `virtual_memory`, `disk_io_counters`, `net_io_counters`,
`process_iter`) rather than any OS-specific bindings.

## What it does

1. **Collect** (`src/collector.py`) — polls system metrics every N seconds and writes
   each sample to a local SQLite database (`data/telemetry.db`), including which
   process was consuming the most CPU at that moment.
2. **Analyze** (`src/analyzer.py`) — flags two kinds of anomalies:
   - **Sustained high usage**: CPU or memory stays above a threshold (80% / 85%) for
     3+ consecutive samples — catches real pressure, not momentary blips.
   - **Statistical spikes**: a disk or network I/O sample is more than 2.5 standard
     deviations above the trailing 10-sample average — catches sudden anomalous jumps.
3. **Report** (`src/report.py`) — writes a text summary (averages, anomalies, top
   offending processes, suggested optimizations) and a matplotlib chart with
   anomalies marked on the timeline.

## Run it

```bash
pip install -r requirements.txt
python src/main.py --duration 60 --interval 2
```

Outputs land in `reports/report.txt` and `reports/telemetry_chart.png`.

## Example output

```
Samples analyzed : 23
Avg CPU / Max CPU: 34.9% / 100.0%
Avg Mem / Max Mem: 6.3% / 6.3%

Anomalies detected: 2
  - [sustained_cpu] CPU >= 80.0% for 8 consecutive samples
  - [spike_disk] Disk I/O spike: 0.09 MB vs trailing 10-sample average

Top CPU-consuming processes (by # samples as top process):
  - python3: 14 samples

Suggested optimizations:
  * Sustained high CPU detected — investigate the top-offending process for
    busy-polling loops or missing backoff/sleep in hot paths.
```

Verified end-to-end: ran the collector while deliberately spinning up a CPU-bound
background process, and confirmed the analyzer correctly flagged the sustained CPU
anomaly and identified the offending process.

## Design choices

- **Two anomaly rules instead of one threshold** — a single instantaneous threshold
  produces noisy false positives from normal momentary spikes (e.g. a process
  launching). Requiring a sustained run of samples above threshold, plus a separate
  statistical-spike rule for burst-y metrics like disk/network I/O, keeps signal
  higher for both step-change and burst-type anomalies.
- **SQLite over flat CSV** — makes it trivial to query/aggregate arbitrary time
  windows later without re-parsing the whole file.
- **No OS-specific APIs** — deliberately built on psutil's cross-platform surface
  rather than `pywin32`/`wmi` so the same code is portable and testable in any
  environment, while still being the exact approach used for Windows telemetry
  collection in production tooling.

## Possible extensions

- Export to Windows Performance Recorder (WPR)/ETW-style trace format
- Per-core CPU breakdown instead of aggregate
- Configurable thresholds via a config file
- Web dashboard instead of static PNG report
