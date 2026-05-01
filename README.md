# Prosperity 4

Research and strategy development repository for the IMC Prosperity trading competition.

This repo includes trading algorithms, market analysis scripts, backtesting experiments, and strategy variants developed across multiple rounds of the competition.

## Competition Result

Placed as an IMC Prosperity 4 finalist, developing algorithmic trading strategies across multiple rounds of simulated exchange data.

## Highlights

- Placed in the roughly around top 12.5% as an IMC Prosperity 4 finalist through iterative strategy development and backtesting
- Built multiple algorithmic trading strategies for simulated exchange data
- Analyzed order book behavior, price trends, and product-specific market patterns
- Used backtesting workflows to compare strategy performance across trading days
- Organized round-specific strategy files, research scripts, and market data
- Tested strategies using both standard and Monte Carlo-style backtesting workflows
  
## Tech Stack

Python, Pandas, NumPy, IMC Prosperity Backtesting Tools

## Dependencies

- Python 3.9+
- [uv](https://github.com/astral-sh/uv) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Rust/Cargo, only needed for the Monte Carlo backtester — `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`

## Setup

This repository contains my strategy code, market data, and analysis scripts. Some workflows depend on external IMC Prosperity backtesting tools that should be cloned separately into the project root if you want to reproduce those runs.

Expected local setup:

```text
Prosperity4/
├── kevin-fu1-backtester/          # optional external standard backtester
├── chrispy-roberts-backtester/    # optional external Monte Carlo backtester
├── imc-round1/                    # Round 1 strategy workspace
├── round4/                        # Round 4 strategy workspace
└── Tutorial/                      # tutorial data and starter experiments
```

The external backtester folders are intentionally not included in this repo. Clone them separately if you want to use those workflows.

### Standard backtester

```bash
cd kevin-fu1-backtester
uv venv
uv sync
source .venv/bin/activate
uv pip install -e .
```

### Monte Carlo backtester

```bash
cd chrispy-roberts-backtester/backtester
uv venv
uv sync
source .venv/bin/activate
uv pip install -e .
```

### Prosperity4btest backtester

```bash
cd imc-round1
python3 -m venv .venv
source .venv/bin/activate
pip install -U prosperity4btest
```

## Running

### Standard backtester

```bash
# Standard backtest, round 0, both days
./run.sh

# Standard backtest, no visualizer
./run.sh --no-vis

# Standard backtest, day -2 only
./run.sh 0 --day -2
```

### Monte Carlo backtester

```bash
# Monte Carlo, 100 sessions
./run.sh mc

# Monte Carlo, 1000 sessions
./run.sh mc heavy
```

### Prosperity4btest backtester

```bash
# Round 1 current trader
prosperity4btest trader.py 1 --merge-pnl

# Round 1 v3 trader
prosperity4btest traders/trader_v3.py 1 --merge-pnl
```

## Output Files

Generated outputs are intentionally excluded from this public repository.

Common output locations:

```text
chrispy-roberts-backtester/tmp/<timestamp>/dashboard.json
backtests/<timestamp>.log
imc-round1/ generated logs, depending on prosperity4btest command options
```

These files are useful locally, but they are not tracked because they can become large and are generated during experiments.

## Data

The included CSV files are IMC Prosperity competition market data used for local analysis and backtesting.

Generated logs, final submissions, local backtest outputs, virtual environments, and machine-specific files are excluded through `.gitignore`.

## Notes

This repository is for research, learning, and competition strategy development. It is not financial advice and is not intended for live trading.
