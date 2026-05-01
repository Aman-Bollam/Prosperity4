# Prosperity 4

Research and strategy development repo for the IMC Prosperity trading competition.

This repo includes trading algorithms, market analysis scripts, backtesting experiments, and strategy variants developed across multiple rounds of the competition.

## Highlights

- Built multiple algorithmic trading strategies for simulated exchange data
- Analyzed order book behavior, price trends, and product-specific market patterns
- Used backtesting workflows to compare strategy performance across trading days
- Organized round-specific strategy files, research scripts, and market data

## Tech Stack

Python, Pandas, NumPy, IMC Prosperity Backtesting Tools
## Dependencies

- Python 3.9+
- [uv](https://github.com/astral-sh/uv) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Rust/Cargo (for Monte Carlo backtester) — `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`

## Setup

Clone with submodules or clone the backtester repos separately into the project root:

```text
Prosperity4/
├── kevin-fu1-backtester/          # standard backtester
├── chrispy-roberts-backtester/    # Monte Carlo backtester
└── imc-round1/                    # prosperity4btest backtester workspace
```

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

```bash
# Standard backtest (round 0, both days)
./run.sh

# Standard backtest, no visualizer
./run.sh --no-vis

# Standard backtest, day -2 only
./run.sh 0 --day -2

# Monte Carlo (100 sessions)
./run.sh mc

# Monte Carlo (1000 sessions)
./run.sh mc heavy
```

### Prosperity4btest backtester

```bash
# Round 1 current trader
prosperity4btest trader.py 1 --merge-pnl

# Round 1 v3 trader
prosperity4btest traders/trader_v3.py 1 --merge-pnl
```

Monte Carlo output is saved to `chrispy-roberts-backtester/tmp/<timestamp>/dashboard.json`.

Standard backtest logs are saved to `backtests/<timestamp>.log`.

Prosperity4btest logs are saved according to the command options you use inside `imc-round1/`.
