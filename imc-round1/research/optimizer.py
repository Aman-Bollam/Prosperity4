
from __future__ import annotations
import argparse
from contextlib import contextmanager
import csv
import itertools
import re
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BACKTESTER = f"{sys.executable} -m prosperity4btest"

PROFIT_RE = re.compile(r"Total profit:\s*([\-0-9,]+)")


@contextmanager
def build_temp_file(src: Path, replacements: list[tuple[str, str]]):
    text = src.read_text()
    for old, new in replacements:
        if old not in text:
            raise ValueError(f"Could not find pattern to replace: {old}")
        text = text.replace(old, new, 1)

    with tempfile.TemporaryDirectory() as temp_dir:
        tmp = Path(temp_dir) / src.name
        tmp.write_text(text)
        yield tmp


def run_backtest(backtester: str, trader_path: Path, round_arg: str, extra_args: list[str] | None = None):
    cmd = [*shlex.split(backtester), str(trader_path), round_arg, "--merge-pnl"]
    if extra_args:
        cmd.extend(extra_args)

    proc = subprocess.run(cmd, capture_output=True, text=True)
    output = (proc.stdout or "") + "\n" + (proc.stderr or "")
    matches = PROFIT_RE.findall(output)
    profit = int(matches[-1].replace(",", "")) if matches else None
    return profit, output


def default_output_path(strategy: str, trader_file: Path, round_arg: str) -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    stem = trader_file.stem
    round_slug = round_arg.replace("/", "_")
    return ROOT / "research" / "results" / f"{strategy}_{stem}_round-{round_slug}_{timestamp}.csv"


def write_results_csv(output_path: Path, results: list[dict[str, object]]) -> None:
    if not results:
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(results[0].keys())
    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)


def optimize_v1(
    trader_file: Path,
    round_arg: str,
    backtester: str,
):
    pepper_sizes = [22, 24, 26]
    pepper_edges = [1, 2]
    osmium_edges = [1, 2, 3]
    osmium_hist = [45, 55, 65]

    best = None
    all_results = []

    for p_size, p_edge, o_edge, o_hist in itertools.product(
        pepper_sizes, pepper_edges, osmium_edges, osmium_hist
    ):
        replacements = [
            ('"base_size": 24,', f'"base_size": {p_size},'),
            ('"take_edge": 1,', f'"take_edge": {p_edge},'),
            ('"history_len": 55,', f'"history_len": {o_hist},'),
            ('"take_edge": 2,', f'"take_edge": {o_edge},'),
        ]
        with build_temp_file(trader_file, replacements) as tmp:
            profit, _ = run_backtest(backtester, tmp, round_arg)
        result = {
            "profit": profit,
            "pepper_base_size": p_size,
            "pepper_take_edge": p_edge,
            "osmium_take_edge": o_edge,
            "osmium_history_len": o_hist,
        }
        all_results.append(result)
        print(result)

        score = -10**18 if profit is None else profit
        if best is None or score > best["profit"]:
            best = result

    print("\nBest config:")
    print(best)
    return best, all_results


def optimize_v3(
    trader_file: Path,
    round_arg: str,
    backtester: str,
):
    pepper_line_windows = [25, 35, 45]
    pepper_quote_offsets = [1, 2]
    osmium_short_windows = [12, 20, 30]
    osmium_long_windows = [60, 80, 120]
    osmium_drift_thresholds = [0.8, 1.2, 1.8]

    best = None
    all_results = []

    for plw, pqo, osw, olw, odt in itertools.product(
        pepper_line_windows,
        pepper_quote_offsets,
        osmium_short_windows,
        osmium_long_windows,
        osmium_drift_thresholds,
    ):
        if osw >= olw:
            continue

        replacements = [
            ('"line_window": 35,', f'"line_window": {plw},'),
            ('"quote_offset_wide": 2,', f'"quote_offset_wide": {pqo},'),
            ('"short_window": 20,', f'"short_window": {osw},'),
            ('"long_window": 80,', f'"long_window": {olw},'),
            ('"drift_threshold": 1.2,', f'"drift_threshold": {odt},'),
        ]
        with build_temp_file(trader_file, replacements) as tmp:
            profit, _ = run_backtest(backtester, tmp, round_arg)
        result = {
            "profit": profit,
            "pepper_line_window": plw,
            "pepper_quote_offset_wide": pqo,
            "osmium_short_window": osw,
            "osmium_long_window": olw,
            "osmium_drift_threshold": odt,
        }
        all_results.append(result)
        print(result)

        score = -10**18 if profit is None else profit
        if best is None or score > best["profit"]:
            best = result

    print("\nBest config:")
    print(best)
    return best, all_results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--file",
        required=True,
        help="Path to the trader file to optimize, e.g. traders/trader_v1.py",
    )
    parser.add_argument(
        "--strategy",
        choices=["v1", "v3"],
        required=True,
        help="Which replacement grid to use",
    )
    parser.add_argument("--round", default="1", help="Round/day argument for the backtester")
    parser.add_argument("--backtester", default=DEFAULT_BACKTESTER)
    parser.add_argument(
        "--out",
        help="CSV file to write optimization results to. Defaults to research/results/<strategy>_<trader>_<timestamp>.csv",
    )
    args = parser.parse_args()

    trader_file = Path(args.file)
    if not trader_file.is_absolute():
        trader_file = (ROOT / trader_file).resolve()

    if not trader_file.exists():
        raise FileNotFoundError(f"Trader file not found: {trader_file}")

    output_path = Path(args.out).expanduser() if args.out else default_output_path(args.strategy, trader_file, args.round)
    if not output_path.is_absolute():
        output_path = (ROOT / output_path).resolve()

    if args.strategy == "v1":
        best, all_results = optimize_v1(trader_file, args.round, args.backtester)
    else:
        best, all_results = optimize_v3(trader_file, args.round, args.backtester)

    write_results_csv(output_path, all_results)
    print(f"\nSaved {len(all_results)} results to {output_path}")


if __name__ == "__main__":
    main()
