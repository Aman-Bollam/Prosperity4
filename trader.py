"""
trader.py — Prosperity 4 Starter Algorithm
==========================================
Round 0 (Tutorial) strategy:
  EMERALDS  → Fixed fair value market maker (fair = 10,000)
  TOMATOES  → Rolling mean-reversion market maker

Run with backtester:
  ./run.sh          → backtest round 0, open in visualizer
  ./run.sh 0 --no-vis
"""

import json
import math
from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, List

from datamodel import Listing, Observation, Order, OrderDepth, ProsperityEncoder, Symbol, Trade, TradingState


# ── Logger (required by visualizer) ──────────────────────────────────────────

class Logger:
    def __init__(self) -> None:
        self.logs = ""
        self.max_log_length = 3750

    def print(self, *objects: Any, sep: str = " ", end: str = "\n") -> None:
        self.logs += sep.join(map(str, objects)) + end

    def flush(self, state: TradingState, orders: dict[Symbol, list[Order]], conversions: int, trader_data: str) -> None:
        base_length = len(self.to_json([self.compress_state(state, ""), self.compress_orders(orders), conversions, "", ""]))
        max_item_length = (self.max_log_length - base_length) // 3
        print(self.to_json([
            self.compress_state(state, self.truncate(state.traderData, max_item_length)),
            self.compress_orders(orders),
            conversions,
            self.truncate(trader_data, max_item_length),
            self.truncate(self.logs, max_item_length),
        ]))
        self.logs = ""

    def compress_state(self, state: TradingState, trader_data: str) -> list[Any]:
        return [state.timestamp, trader_data, self.compress_listings(state.listings),
                self.compress_order_depths(state.order_depths), self.compress_trades(state.own_trades),
                self.compress_trades(state.market_trades), state.position, self.compress_observations(state.observations)]

    def compress_listings(self, listings: dict[Symbol, Listing]) -> list[list[Any]]:
        return [[l.symbol, l.product, l.denomination] for l in listings.values()]

    def compress_order_depths(self, order_depths: dict[Symbol, OrderDepth]) -> dict[Symbol, list[Any]]:
        return {s: [od.buy_orders, od.sell_orders] for s, od in order_depths.items()}

    def compress_trades(self, trades: dict[Symbol, list[Trade]]) -> list[list[Any]]:
        return [[t.symbol, t.price, t.quantity, t.buyer, t.seller, t.timestamp]
                for arr in trades.values() for t in arr]

    def compress_observations(self, observations: Observation) -> list[Any]:
        conversion_observations = {
            p: [o.bidPrice, o.askPrice, o.transportFees, o.exportTariff, o.importTariff, o.sugarPrice, o.sunlightIndex]
            for p, o in observations.conversionObservations.items()
        }
        return [observations.plainValueObservations, conversion_observations]

    def compress_orders(self, orders: dict[Symbol, list[Order]]) -> list[list[Any]]:
        return [[o.symbol, o.price, o.quantity] for arr in orders.values() for o in arr]

    def to_json(self, value: Any) -> str:
        return json.dumps(value, cls=ProsperityEncoder, separators=(",", ":"))

    def truncate(self, value: str, max_length: int) -> str:
        lo, hi = 0, min(len(value), max_length)
        out = ""
        while lo <= hi:
            mid = (lo + hi) // 2
            candidate = value[:mid]
            if len(candidate) < len(value):
                candidate += "..."
            if len(json.dumps(candidate)) <= max_length:
                out = candidate
                lo = mid + 1
            else:
                hi = mid - 1
        return out


logger = Logger()


# ── Strategy configs ──────────────────────────────────────────────────────────

@dataclass
class FixedFairConfig:
    """Market maker around a known fixed fair value (e.g. EMERALDS)."""
    fair_value: int
    spread: int = 2          # quote fair ± spread
    order_size: int = 10
    position_limit: int = 80


@dataclass
class TomatoConfig:
    """Microprice + EMA + vol-scaled market maker."""
    # EMA for fair value
    ema_window: int = 10
    # Volatility
    vol_lookback: int = 20
    vol_floor: float = 1.0
    # Order book imbalance
    imbalance_weight: float = 0.3
    imb_depth_eps: float = 0.001  # epsilon for depth-weighted imbalance
    imb_momentum_weight: float = 0.0  # weight on imbalance momentum (0 = off)
    # Aggressive taking: edge = vol * edge_frac
    edge_frac: float = 0.15
    # Spread capture regime
    sc_z_thresh: float = 0.3
    sc_trend_mult: float = 2.0
    sc_vol_cap: float = 5.0
    # Signal (z-score directional)
    signal_z_thresh: float = 1.2
    signal_base_frac: float = 0.2
    signal_z_frac: float = 0.2
    # Market making
    spread_frac: float = 0.7
    spread_floor: int = 2
    inv_skew: float = 3.0
    z_skew: float = 0.2
    mm_scale_after_take: float = 0.5
    # Inventory management
    soft_limit_frac: float = 1.0   # start reducing passive size above this fraction (1.0 = off)
    inv_urgency: float = 0.0       # cubic skew acceleration near limits (0 = off)
    stale_thresh: int = 999        # ticks at high inventory before widening spread (999 = off)
    stale_spread_add: float = 0.0  # spread widening per stale tick
    # History
    hist_maxlen: int = 100
    position_limit: int = 80


PRODUCT_CONFIG: Dict[str, Any] = {
    "EMERALDS": FixedFairConfig(fair_value=10_000, spread=7, order_size=20),
    "TOMATOES": TomatoConfig(),
}


# ── Trader ────────────────────────────────────────────────────────────────────

class Trader:

    def __init__(self):
        self._state: Dict[str, Any] = {}  # persisted across ticks

    def run(self, state: TradingState):
        if state.traderData:
            try:
                self._state = json.loads(state.traderData)
            except Exception:
                self._state = {}

        orders: Dict[str, List[Order]] = {}
        for product, depth in state.order_depths.items():
            cfg = PRODUCT_CONFIG.get(product)
            if cfg is None:
                continue
            pos = state.position.get(product, 0)

            if isinstance(cfg, FixedFairConfig):
                orders[product] = self._fixed_fair(product, depth, pos, cfg)
            elif isinstance(cfg, TomatoConfig):
                orders[product] = self._trade_tomatoes(product, depth, pos, cfg)

        trader_data_str = json.dumps(self._state)
        logger.flush(state, orders, 0, trader_data_str)
        return orders, 0, trader_data_str

    # ── Fixed fair value market maker ─────────────────────────────────────────
    def _fixed_fair(self, product: str, depth: OrderDepth, pos: int, cfg: FixedFairConfig) -> List[Order]:
        orders = []
        fair = cfg.fair_value
        limit = cfg.position_limit

        # Strictly below fair: always take (clear edge)
        # At fair: only take when it REDUCES inventory
        for ask_price, ask_vol in sorted(depth.sell_orders.items()):
            if ask_price < fair:
                qty = min(limit - pos, -ask_vol)
                if qty > 0:
                    orders.append(Order(product, ask_price, qty))
                    pos += qty
            elif ask_price == fair and pos < 0:
                qty = min(-pos, -ask_vol)   # reduce short only
                if qty > 0:
                    orders.append(Order(product, ask_price, qty))
                    pos += qty

        for bid_price, bid_vol in sorted(depth.buy_orders.items(), reverse=True):
            if bid_price > fair:
                qty = min(limit + pos, bid_vol)
                if qty > 0:
                    orders.append(Order(product, bid_price, -qty))
                    pos -= qty
            elif bid_price == fair and pos > 0:
                qty = min(pos, bid_vol)     # reduce long only
                if qty > 0:
                    orders.append(Order(product, bid_price, -qty))
                    pos -= qty

        # Passive quotes
        buy_qty = min(cfg.order_size, limit - pos)
        sell_qty = min(cfg.order_size, limit + pos)
        if buy_qty > 0:
            orders.append(Order(product, fair - cfg.spread, buy_qty))
        if sell_qty > 0:
            orders.append(Order(product, fair + cfg.spread, -sell_qty))

        return orders

    # ── TOMATOES: microprice + Kalman + vol-scaled MM ──────────────────────
    @staticmethod
    def _ema(prices: list, window: int) -> float:
        if not prices:
            return 0.0
        w = min(window, len(prices))
        alpha = 2 / (w + 1)
        val = sum(prices[:w]) / w
        for p in prices[w:]:
            val = alpha * p + (1 - alpha) * val
        return val

    @staticmethod
    def _std(values: list) -> float:
        if len(values) < 2:
            return 0.0
        m = sum(values) / len(values)
        return math.sqrt(sum((x - m) ** 2 for x in values) / (len(values) - 1))

    def _trade_tomatoes(self, product: str, depth: OrderDepth, pos: int, cfg: TomatoConfig) -> List[Order]:
        orders: List[Order] = []
        limit = cfg.position_limit

        if not depth.buy_orders or not depth.sell_orders:
            return orders

        best_bid = max(depth.buy_orders)
        best_ask = min(depth.sell_orders)
        bid_vol = depth.buy_orders[best_bid]
        ask_vol = abs(depth.sell_orders[best_ask])

        # ── Microprice (level 1) ──
        total = max(1, bid_vol + ask_vol)
        microprice = (best_bid * ask_vol + best_ask * bid_vol) / total

        # ── Multi-level depth-weighted imbalance (from HFT PDF) ──
        # Q = sum over levels: weight(distance) * volume
        # weight(d) = 1 / (d + eps), d = |price - best| / best
        eps = cfg.imb_depth_eps
        q_bid = 0.0
        for price, vol_at in depth.buy_orders.items():
            d = abs(price - best_bid) / best_bid
            q_bid += vol_at / (d + eps)
        q_ask = 0.0
        for price, vol_at in depth.sell_orders.items():
            d = abs(price - best_ask) / best_ask
            q_ask += abs(vol_at) / (d + eps)
        q_total = max(1.0, q_bid + q_ask)
        imbalance = (q_bid - q_ask) / q_total

        # ── Imbalance momentum (track last 3 ticks) ──
        imb_hist = self._state.get("imb_hist", [])
        imb_hist.append(imbalance)
        imb_hist = imb_hist[-3:]
        self._state["imb_hist"] = imb_hist
        if len(imb_hist) >= 3 and cfg.imb_momentum_weight > 0:
            imb_momentum = imb_hist[-1] - imb_hist[-3]
            imbalance = imbalance + cfg.imb_momentum_weight * imb_momentum

        # ── History ──
        hist = self._state.get("hist", [])
        hist.append(microprice)
        hist = hist[-cfg.hist_maxlen:]
        self._state["hist"] = hist

        # ── EMA + imbalance fair value ──
        ema = self._ema(hist, cfg.ema_window)

        # ── Realized volatility ──
        diffs = [hist[i] - hist[i - 1] for i in range(1, len(hist))]
        vol = self._std(diffs[-cfg.vol_lookback:]) if len(diffs) > 5 else 2.0
        vol = max(vol, cfg.vol_floor)

        fair = ema + cfg.imbalance_weight * imbalance * vol

        z = (microprice - fair) / vol

        # ── Trend detection ──
        trend = hist[-1] - hist[-5] if len(hist) >= 5 else 0.0
        is_trending = abs(trend) > cfg.sc_trend_mult * vol

        took_liquidity = False

        # ── Spread capture: calm market regime ──
        if abs(z) < cfg.sc_z_thresh and not is_trending and vol < cfg.sc_vol_cap:
            buy_qty = max(0, limit - pos)
            sell_qty = max(0, limit + pos)
            if buy_qty > 0:
                orders.append(Order(product, best_bid + 1, buy_qty))
            if sell_qty > 0:
                orders.append(Order(product, best_ask - 1, -sell_qty))
            return orders

        # ── Aggressive taking ──
        edge = max(1, int(vol * cfg.edge_frac))

        for ask in sorted(depth.sell_orders):
            if ask < fair - edge and pos < limit:
                qty = min(abs(depth.sell_orders[ask]), limit - pos)
                orders.append(Order(product, ask, qty))
                pos += qty
                took_liquidity = True

        for bid in sorted(depth.buy_orders, reverse=True):
            if bid > fair + edge and pos > -limit:
                qty = min(depth.buy_orders[bid], limit + pos)
                orders.append(Order(product, bid, -qty))
                pos -= qty
                took_liquidity = True

        # ── Z-score directional signal (mean reversion when not trending) ──
        if not is_trending:
            size = int(limit * (cfg.signal_base_frac + cfg.signal_z_frac * min(1, abs(z))))
            if z > cfg.signal_z_thresh and pos > -limit:
                qty = min(size, limit + pos)
                if qty > 0:
                    orders.append(Order(product, best_bid, -qty))
                    pos -= qty
            elif z < -cfg.signal_z_thresh and pos < limit:
                qty = min(size, limit - pos)
                if qty > 0:
                    orders.append(Order(product, best_ask, qty))
                    pos += qty

        # ── Stale inventory tracking ──
        soft_limit = int(limit * cfg.soft_limit_frac)
        stale = self._state.get("stale_ticks", 0)
        if abs(pos) > soft_limit:
            stale += 1
        else:
            stale = 0
        self._state["stale_ticks"] = stale

        # ── Passive market making ──
        mm_scale = cfg.mm_scale_after_take if took_liquidity else 1.0

        spread = max(cfg.spread_floor, int(vol * cfg.spread_frac))

        # Widen spread when inventory is stale
        if stale > cfg.stale_thresh:
            spread += int((stale - cfg.stale_thresh) * cfg.stale_spread_add)

        # Nonlinear inventory urgency: cubic term accelerates near limits
        inv = pos / limit
        skew = int(-(inv + inv ** 3 * cfg.inv_urgency) * cfg.inv_skew - z * cfg.z_skew)

        buy_price = min(best_bid + 1, int(fair - spread + skew))
        sell_price = max(best_ask - 1, int(fair + spread + skew))

        if buy_price >= sell_price:
            buy_price, sell_price = int(fair - 1), int(fair + 1)

        buy_qty = max(0, int((limit - pos) * mm_scale))
        sell_qty = max(0, int((limit + pos) * mm_scale))

        # Soft position limit: reduce size on worsening side
        if pos > soft_limit and buy_qty > 0:
            buy_qty = max(1, int(buy_qty * (limit - pos) / max(1, limit - soft_limit)))
        elif pos < -soft_limit and sell_qty > 0:
            sell_qty = max(1, int(sell_qty * (limit + pos) / max(1, limit - soft_limit)))

        if buy_qty > 0:
            orders.append(Order(product, buy_price, buy_qty))
        if sell_qty > 0:
            orders.append(Order(product, sell_price, -sell_qty))

        return orders
