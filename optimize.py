"""
optimize.py — Grid search over TOMATOES hyperparameters.
Usage:
  python optimize.py              # full grid search
  python optimize.py --quick      # reduced grid
"""

import sys
import itertools
from dataclasses import replace
from pathlib import Path
from contextlib import redirect_stdout
from io import StringIO

sys.path.insert(0, str(Path(__file__).parent / "imc-prosperity-4-backtester"))
sys.path.insert(0, str(Path(__file__).parent / "imc-prosperity-4-backtester" / "prosperity4bt"))

from prosperity4bt.tools.data_reader import PackageResourcesReader
from prosperity4bt.test_runner import TestRunner
from prosperity4bt.models.test_options import TradeMatchingMode

import trader as trader_module


def run_backtest(config_overrides: dict) -> dict:
    original_cfg = trader_module.PRODUCT_CONFIG["TOMATOES"]
    patched = replace(original_cfg, **config_overrides)
    trader_module.PRODUCT_CONFIG["TOMATOES"] = patched

    data_reader = PackageResourcesReader()
    total_pnl = {}

    for day in [-2, -1]:
        t = trader_module.Trader()
        runner = TestRunner(t, data_reader, 0, day,
                            show_progress_bar=False, print_output=False,
                            trade_matching_mode=TradeMatchingMode.all)
        with redirect_stdout(StringIO()):
            result = runner.run()
        for act in result.final_activities():
            total_pnl[act.symbol] = total_pnl.get(act.symbol, 0) + act.profit_loss

    trader_module.PRODUCT_CONFIG["TOMATOES"] = original_cfg
    return total_pnl


def phase_search(name: str, grid: dict, fixed: dict) -> tuple:
    keys = list(grid.keys())
    combos = list(itertools.product(*[grid[k] for k in keys]))
    print(f"Testing {len(combos)} combinations...", flush=True)

    best_pnl = -float("inf")
    best_params = {}
    results = []

    for i, values in enumerate(combos):
        params = {**fixed, **dict(zip(keys, values))}
        try:
            pnl = run_backtest(params)
            t_pnl = pnl.get("TOMATOES", 0)
            results.append((t_pnl, params))
            if t_pnl > best_pnl:
                best_pnl = t_pnl
                best_params = params.copy()
            if (i + 1) % 25 == 0:
                print(f"  [{i+1}/{len(combos)}] best: {best_pnl:,.0f}", flush=True)
        except Exception as e:
            print(f"  Error: {e}", flush=True)

    results.sort(key=lambda x: x[0], reverse=True)
    print(f"\n{name} best: TOMATOES PnL = {best_pnl:,.0f}", flush=True)
    for pnl, params in results[:5]:
        varied = {k: params[k] for k in keys}
        print(f"  {pnl:,.0f} | {varied}", flush=True)
    sys.stdout.flush()
    return best_pnl, best_params


def grid_search(quick: bool = False):
    # Phase 1: Fair value (EMA + imbalance + vol)
    print("=" * 70, flush=True)
    print("PHASE 1: Fair value estimation", flush=True)
    print("=" * 70, flush=True)

    if quick:
        p1 = {
            "ema_window": [5, 8, 10],
            "imbalance_weight": [0.2, 0.3, 0.5],
            "imb_depth_eps": [0.001, 0.1],
            "imb_momentum_weight": [0.0, 0.3],
            "vol_lookback": [10, 20],
            "vol_floor": [0.5, 1.0],
        }
    else:
        p1 = {
            "ema_window": [3, 5, 8, 10, 15, 20],
            "imbalance_weight": [0.0, 0.1, 0.2, 0.3, 0.5, 0.8],
            "imb_depth_eps": [0.0001, 0.001, 0.01, 0.1, 1.0],
            "imb_momentum_weight": [0.0, 0.1, 0.3, 0.5, 1.0],
            "vol_lookback": [5, 10, 15, 20, 30],
            "vol_floor": [0.5, 1.0, 1.5, 2.0],
        }

    _, best1 = phase_search("Phase 1", p1, {})

    # Phase 2: Spread capture + taking
    print("\n" + "=" * 70, flush=True)
    print("PHASE 2: Spread capture + taking", flush=True)
    print("=" * 70, flush=True)

    fixed2 = {k: best1[k] for k in p1}
    if quick:
        p2 = {
            "edge_frac": [0.1, 0.15, 0.2, 0.3],
            "sc_z_thresh": [0.2, 0.3, 0.5],
            "sc_trend_mult": [1.5, 2.0, 3.0],
            "sc_vol_cap": [3.0, 5.0, 8.0],
        }
    else:
        p2 = {
            "edge_frac": [0.05, 0.1, 0.15, 0.2, 0.3, 0.5],
            "sc_z_thresh": [0.1, 0.2, 0.3, 0.5, 0.8],
            "sc_trend_mult": [1.0, 1.5, 2.0, 3.0],
            "sc_vol_cap": [2.0, 3.0, 5.0, 8.0, 12.0],
        }

    _, best2 = phase_search("Phase 2", p2, fixed2)

    # Phase 3: Signal + MM + inventory management
    print("\n" + "=" * 70, flush=True)
    print("PHASE 3: Signal + MM + inventory management", flush=True)
    print("=" * 70, flush=True)

    fixed3 = {k: best2[k] for k in list(p1) + list(p2)}
    if quick:
        p3 = {
            "signal_z_thresh": [1.0, 1.2, 1.5],
            "spread_frac": [0.5, 0.7, 1.0],
            "spread_floor": [2, 3],
            "inv_skew": [2.0, 3.0, 4.0],
            "mm_scale_after_take": [0.3, 0.5, 1.0],
            "soft_limit_frac": [0.6, 0.8, 1.0],
            "inv_urgency": [0.0, 1.0, 2.0],
        }
    else:
        p3 = {
            "signal_z_thresh": [0.6, 0.8, 1.0, 1.2, 1.5, 2.0],
            "signal_base_frac": [0.1, 0.2, 0.3],
            "signal_z_frac": [0.1, 0.2, 0.3],
            "spread_frac": [0.3, 0.5, 0.7, 1.0, 1.5],
            "spread_floor": [1, 2, 3, 4],
            "inv_skew": [1.0, 2.0, 3.0, 4.0, 5.0],
            "z_skew": [0.0, 0.1, 0.2, 0.3, 0.5],
            "mm_scale_after_take": [0.3, 0.5, 0.7, 1.0],
            "soft_limit_frac": [0.5, 0.6, 0.8, 1.0],
            "inv_urgency": [0.0, 0.5, 1.0, 2.0],
            "stale_thresh": [3, 5, 10, 999],
            "stale_spread_add": [0.0, 0.3, 0.5, 1.0],
        }

    _, best3 = phase_search("Phase 3", p3, fixed3)

    # Final report
    print("\n" + "=" * 70, flush=True)
    print("FINAL BEST CONFIG", flush=True)
    print("=" * 70, flush=True)
    all_keys = list(p1) + list(p2) + list(p3)
    final_overrides = {k: best3[k] for k in all_keys}
    final_pnl = run_backtest(final_overrides)
    print(f"TOMATOES PnL: {final_pnl.get('TOMATOES', 0):,.0f}", flush=True)
    print(f"EMERALDS PnL: {final_pnl.get('EMERALDS', 0):,.0f}", flush=True)
    print(f"Total PnL:    {sum(final_pnl.values()):,.0f}", flush=True)
    print(f"\nTomatoConfig(", flush=True)
    for k, v in final_overrides.items():
        print(f"    {k}={v},", flush=True)
    print(f")", flush=True)
    sys.stdout.flush()

    return final_overrides


if __name__ == "__main__":
    quick = "--quick" in sys.argv
    grid_search(quick=quick)
