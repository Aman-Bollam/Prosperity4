# Round 1 notes

## Products
- `INTARIAN_PEPPER_ROOT`
  - behaves more like a steady asset with a positive slope than a true constant-fair asset
  - likely worth testing rolling line-fit fair values
- `ASH_COATED_OSMIUM`
  - likely an asset with drift / regime changes
  - worth testing short-vs-long moving-average regime logic

## Current baseline
- `traders/trader_v1.py`
- also copied to top-level `trader.py` for convenience

## Experiments so far
- `trader_v2.py`
  - more aggressive passive sizing and tighter quotes
  - backtested worse than v1
- next test:
  - `trader_v3.py`
  - Pepper line-fit fair
  - Osmium drift/regime logic

## Workflow
1. Edit one trader file
2. Run `prosperity4btest ... --merge-pnl`
3. Save logs into `backtests/`
4. Record product-level and merged PnL here
5. Only keep changes that improve merged PnL and do not break one product badly

## To-do
- try Pepper `base_size` 26 without other changes
- try Osmium `take_edge` = 1 and 3 separately
- test line-fit Pepper in v3
- test drift-threshold and short/long windows in v3
