"""
main.py
CLI entrypoint: collect telemetry for N seconds, analyze it, and write a report + chart.

Usage:
    python src/main.py --duration 60 --interval 2
"""
import argparse
from pathlib import Path

from collector import run_collector, DB_PATH
import report as report_mod


def main():
    parser = argparse.ArgumentParser(description="Windows/Cross-platform system telemetry & performance analyzer")
    parser.add_argument("--duration", type=int, default=60, help="Collection duration in seconds")
    parser.add_argument("--interval", type=float, default=2.0, help="Seconds between samples")
    args = parser.parse_args()

    print(f"Collecting telemetry for {args.duration}s (interval {args.interval}s)...")
    n = run_collector(args.duration, args.interval)
    print(f"Collected {n} samples.")

    print("Analyzing and generating report...")
    report_txt, txt_path, png_path = report_mod.generate()
    print(report_txt)
    print(f"\nReport: {txt_path}")
    print(f"Chart:  {png_path}")


if __name__ == "__main__":
    main()
