from __future__ import annotations
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKTEST_DIR = ROOT / "backtests"

DAY_RE = re.compile(r"round 1 day ([\-0-9]+)")
PROFIT_RE = re.compile(r"Total profit:\s*([\-0-9,]+)")
PRODUCT_RE = re.compile(r"^(ASH_COATED_OSMIUM|INTARIAN_PEPPER_ROOT):\s*([\-0-9,]+)$")


def parse_log(path: Path):
    text = path.read_text(errors="ignore")
    day = DAY_RE.search(text)
    total = PROFIT_RE.findall(text)
    products = PRODUCT_RE.findall(text)
    return {
        "file": path.name,
        "day": day.group(1) if day else "?",
        "total_profit": int(total[-1].replace(",", "")) if total else None,
        "products": {name: int(val.replace(",", "")) for name, val in products},
    }


def main():
    logs = sorted(BACKTEST_DIR.glob("*.log"))
    if not logs:
        print("No logs found in backtests/.")
        return

    for log in logs:
        parsed = parse_log(log)
        print(parsed["file"])
        print(f"  day: {parsed['day']}")
        print(f"  total_profit: {parsed['total_profit']}")
        for product, pnl in parsed["products"].items():
            print(f"  {product}: {pnl}")
        print()


if __name__ == "__main__":
    main()
