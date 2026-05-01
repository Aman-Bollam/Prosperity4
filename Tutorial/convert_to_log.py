"""
convert_to_log.py
=================
Converts raw Prosperity prices_*.csv + trades_*.csv files into a single
.log file that the dashboard can load directly.

Usage:
    python convert_to_log.py                        # auto-finds all CSVs in current dir
    python convert_to_log.py --out mydata.log       # custom output filename
    python convert_to_log.py --dir ./data           # look in a specific folder

Output: prosperity_data.log (or whatever you set with --out)
"""

import argparse
import glob
import os
import sys


def find_csv_pairs(directory: str):
    """
    Find all matching prices_*.csv / trades_*.csv pairs in a directory.
    Returns list of (prices_path, trades_path, label) sorted by round+day.
    """
    price_files = sorted(glob.glob(os.path.join(directory, "prices_*.csv")))
    pairs = []

    for prices_path in price_files:
        basename = os.path.basename(prices_path)
        # prices_round_0_day_-2.csv -> trades_round_0_day_-2.csv
        trades_path = prices_path.replace("prices_", "trades_")
        label = basename.replace("prices_", "").replace(".csv", "")

        if not os.path.exists(trades_path):
            print(f"Warning: no matching trades file for {basename}, skipping")
            continue

        pairs.append((prices_path, trades_path, label))

    return pairs


def convert(pairs, output_path: str):
    """
    Write a combined .log file in the format the dashboard expects:

        Sandbox logs:
        (empty — no algo was run, just raw data)

        Activities log:
        day;timestamp;product;bid_price_1;...;mid_price;profit_and_loss
        ...rows...


        Trade History:
        timestamp;buyer;seller;symbol;currency;price;quantity
        ...rows...
    """

    all_activity_lines = []
    all_trade_lines = []

    ACTIVITY_HEADER = (
        "day;timestamp;product;"
        "bid_price_1;bid_volume_1;bid_price_2;bid_volume_2;bid_price_3;bid_volume_3;"
        "ask_price_1;ask_volume_1;ask_price_2;ask_volume_2;ask_price_3;ask_volume_3;"
        "mid_price;profit_and_loss"
    )

    TRADE_HEADER = "timestamp;buyer;seller;symbol;currency;price;quantity"

    for prices_path, trades_path, label in pairs:
        print(f"  Loading {label}...")

        # --- Activity rows (prices file) ---
        with open(prices_path, "r") as f:
            lines = f.readlines()

        # Skip header, keep data rows
        header = lines[0].strip().lower()
        if "bid_price_1" not in header:
            print(f"    Warning: unexpected header in {prices_path}, skipping")
            continue

        for line in lines[1:]:
            line = line.strip()
            if line:
                all_activity_lines.append(line)

        # --- Trade rows ---
        with open(trades_path, "r") as f:
            tlines = f.readlines()

        theader = tlines[0].strip().lower()
        if "timestamp" not in theader:
            print(f"    Warning: unexpected header in {trades_path}, skipping")
            continue

        for line in tlines[1:]:
            line = line.strip()
            if line:
                all_trade_lines.append(line)

    # --- Write output ---
    with open(output_path, "w", encoding="utf-8") as out:
        # Section 1: Sandbox logs (empty for raw data)
        out.write("Sandbox logs:\n\n\n")

        # Section 2: Activities log
        out.write("Activities log:\n")
        out.write(ACTIVITY_HEADER + "\n")
        out.write("\n".join(all_activity_lines))

        # Section 3: Trade History
        out.write("\n\n\n\n\nTrade History:\n")
        out.write(TRADE_HEADER + "\n")
        out.write("\n".join(all_trade_lines))
        out.write("\n")

    n_activity = len(all_activity_lines)
    n_trades = len(all_trade_lines)
    print(f"\n✓ Written to: {output_path}")
    print(f"  {n_activity} activity rows")
    print(f"  {n_trades} trade rows")


def main():
    parser = argparse.ArgumentParser(description="Convert Prosperity CSVs to dashboard .log format")
    parser.add_argument("--dir", default=".", help="Directory containing the CSV files (default: current dir)")
    parser.add_argument("--out", default="prosperity_data.log", help="Output log filename (default: prosperity_data.log)")
    args = parser.parse_args()

    directory = os.path.abspath(args.dir)
    print(f"Looking for CSV pairs in: {directory}")

    pairs = find_csv_pairs(directory)

    if not pairs:
        print("No matching prices_*.csv / trades_*.csv pairs found.")
        print("Make sure your files are named like:")
        print("  prices_round_0_day_-2.csv")
        print("  trades_round_0_day_-2.csv")
        sys.exit(1)

    print(f"Found {len(pairs)} pair(s):")
    for _, _, label in pairs:
        print(f"  • {label}")
    print()

    convert(pairs, args.out)


if __name__ == "__main__":
    main()