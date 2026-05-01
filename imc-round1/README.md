# IMC Round 1 repo

This is a lightweight team repo layout for Prosperity Round 1.

## Structure

- `trader.py`
  - current best submission file
- `traders/`
  - experiment trader versions
- `research/`
  - simple scripts for CSV analysis, log parsing, and parameter sweeps
- `backtests/`
  - saved backtest logs
- `data/`
  - Round 1 CSVs

## Current files

### Traders
- `trader_baseline.py`
  - simple baseline skeleton
- `trader_v1.py`
  - current best baseline from local tests
- `trader_v2.py`
  - more aggressive version that underperformed
- `trader_pepper_line.py`
  - isolated Pepper line-fit experiment
- `trader_osmium_drift.py`
  - isolated Osmium regime experiment
- `trader_v3.py`
  - combined Pepper-line + Osmium-drift architecture

### Research
- `analyze_prices.py`
  - summarize public Round 1 price CSVs
- `analyze_logs.py`
  - parse saved backtest logs
- `optimizer.py`
  - small brute-force sweeps around selected trader parameters
- `notes.md`
  - short findings / experiment notes

## Quick start

Create and activate a venv, then install the backtester:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U prosperity4btest
```

The backtester used here is `prosperity4btest` from:

- https://github.com/nabayansaha/imc-prosperity-4-backtester

That project documents the PyPI distribution and CLI as `prosperity4btest`, while the
underlying Python module is `prosperity4bt`.

Check that the install worked:

```bash
python -m pip show prosperity4btest
python -m prosperity4bt --help
```

Run the current best trader:

```bash
prosperity4btest trader.py 1 --merge-pnl
```

If you prefer module syntax, use:

```bash
python -m prosperity4bt trader.py 1 --merge-pnl
```

This repo also includes a local compatibility shim, so `python -m prosperity4btest ...`
works here even though the installed importable module is actually `prosperity4bt`.

Run another trader file by passing its path:

```bash
prosperity4btest traders/trader_v3.py 1 --merge-pnl
python -m prosperity4btest traders/trader_v3.py 1 --merge-pnl
```

Run the v3 experiment:

```bash
prosperity4btest traders/trader_v3.py 1 --merge-pnl
```

Analyze price CSVs:

```bash
python research/analyze_prices.py
```

Parse saved backtest logs:

```bash
python research/analyze_logs.py
```

Run optimizer examples:

```bash
python research/optimizer.py --mode baseline --round 1
python research/optimizer.py --mode v3 --round 1
```

## Recommendation

Use `trader_v1.py` as the current benchmark. Only replace `trader.py` after a new version clearly beats it on merged PnL and does not blow up one product.
