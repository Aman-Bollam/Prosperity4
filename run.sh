#!/bin/bash
# Usage:
#   ./run.sh          → backtest round 0, open in visualizer
#   ./run.sh --no-vis → backtest round 0, skip visualizer
#   ./run.sh 0--2     → backtest round 0 day -2 only
#   ./run.sh mc       → Monte Carlo backtest (100 sessions)
#   ./run.sh mc heavy → Monte Carlo backtest (1000 sessions)

if [ "$1" = "mc" ]; then
  PRESET="--quick"
  [ "$2" = "heavy" ] && PRESET="--heavy"
  source "$HOME/.cargo/env"
  source "$(dirname "$0")/chrispy-roberts-backtester/backtester/.venv/bin/activate"
  cd "$(dirname "$0")/chrispy-roberts-backtester"
  prosperity4mcbt ../trader.py $PRESET --out tmp/$(date +%Y-%m-%d_%H-%M-%S)/dashboard.json
  exit 0
fi

ROUND=${1:-0}
EXTRA_FLAGS="${@:2}"

cd "$(dirname "$0")/kevin-fu1-backtester"
PYTHONPATH=prosperity4bt python3 -m prosperity4bt \
  ../trader.py $ROUND \
  --out ../backtests/$(date +%Y-%m-%d_%H-%M-%S).log \
  $EXTRA_FLAGS
