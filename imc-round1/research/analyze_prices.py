from __future__ import annotations
import csv
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

PRODUCTS = ["INTARIAN_PEPPER_ROOT", "ASH_COATED_OSMIUM"]


def read_price_rows(path: Path):
    rows = []
    with path.open() as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            rows.append(row)
    return rows


def best_bid_ask(row: dict) -> tuple[float | None, float | None]:
    best_bid = None
    best_ask = None
    for i in range(1, 4):
        bp = row.get(f"bid_price_{i}")
        ap = row.get(f"ask_price_{i}")
        if bp not in (None, ""):
            val = float(bp)
            best_bid = val if best_bid is None else max(best_bid, val)
        if ap not in (None, ""):
            val = float(ap)
            best_ask = val if best_ask is None else min(best_ask, val)
    return best_bid, best_ask


def summarize_file(path: Path):
    rows = read_price_rows(path)
    out = {}
    for product in PRODUCTS:
        mids = []
        spreads = []
        for row in rows:
            if row["product"] != product:
                continue
            bid, ask = best_bid_ask(row)
            if bid is None or ask is None:
                continue
            mids.append((bid + ask) / 2.0)
            spreads.append(ask - bid)
        if mids:
            out[product] = {
                "n": len(mids),
                "mid_mean": round(mean(mids), 3),
                "mid_median": round(median(mids), 3),
                "mid_min": round(min(mids), 3),
                "mid_max": round(max(mids), 3),
                "spread_mean": round(mean(spreads), 3),
                "spread_median": round(median(spreads), 3),
            }
    return out


def main():
    for path in sorted(DATA_DIR.glob("prices_round_1_day_*.csv")):
        print(f"=== {path.name} ===")
        summary = summarize_file(path)
        for product, stats in summary.items():
            print(product)
            for k, v in stats.items():
                print(f"  {k}: {v}")
        print()


if __name__ == "__main__":
    main()
