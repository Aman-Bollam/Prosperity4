"""
trader.py — Prosperity 4 Round 4
gg
Products:
  VELVETFRUIT_EXTRACT  — underlying, mid-anchored MM
  HYDROGEL_PACK        — independent, mid-anchored MM
  VEV_<strike>         — call vouchers; fair = intrinsic + smoothed_premium,
                         where smoothed_premium = EMA(own_mid - intrinsic).
                         Anchors the directional component to S (intrinsic
                         updates instantly) while heavily smoothing the
                         time-value component to limit adverse selection.

Run:
  prosperity4btest round4/trader.py 4 --merge-pnl
"""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from datamodel import Order, OrderDepth, TradingState


UNDERLYING = "VELVETFRUIT_EXTRACT"
HYDROGEL = "HYDROGEL_PACK"

VEV_STRIKES: Dict[str, int] = {
    "VEV_4000": 4000, "VEV_4500": 4500, "VEV_5000": 5000,
    "VEV_5100": 5100, "VEV_5200": 5200, "VEV_5300": 5300,
    "VEV_5400": 5400, "VEV_5500": 5500, "VEV_6000": 6000,
    "VEV_6500": 6500,
}


@dataclass
class MMConfig:
    position_limit: int = 50
    spread: int = 2
    order_size: int = 15
    inv_skew: float = 2.0
    take_edge: int = 1


PRODUCT_CFG: Dict[str, MMConfig] = {
    UNDERLYING: MMConfig(position_limit=50, spread=2, order_size=15, inv_skew=2.0, take_edge=1),
    HYDROGEL:   MMConfig(position_limit=50, spread=3, order_size=15, inv_skew=2.0, take_edge=1),
    **{name: MMConfig(position_limit=80, spread=2, order_size=8, inv_skew=1.5, take_edge=2)
       for name in VEV_STRIKES},
}


class Trader:
    def __init__(self) -> None:
        self._state: Dict[str, Any] = {}

    @staticmethod
    def _mid(depth: OrderDepth) -> Optional[float]:
        if not depth.buy_orders or not depth.sell_orders:
            return None
        return (max(depth.buy_orders) + min(depth.sell_orders)) / 2.0

    def _ema(self, key: str, x: float, alpha: float = 0.2) -> float:
        prev = self._state.get(key)
        ema = x if prev is None else alpha * x + (1 - alpha) * prev
        self._state[key] = ema
        return ema

    def _mm(self, product: str, depth: OrderDepth, pos: int, fair: float, cfg: MMConfig) -> List[Order]:
        orders: List[Order] = []
        limit = cfg.position_limit

        for ask in sorted(depth.sell_orders):
            if ask <= fair - cfg.take_edge and pos < limit:
                qty = min(-depth.sell_orders[ask], limit - pos)
                if qty > 0:
                    orders.append(Order(product, ask, qty))
                    pos += qty
        for bid in sorted(depth.buy_orders, reverse=True):
            if bid >= fair + cfg.take_edge and pos > -limit:
                qty = min(depth.buy_orders[bid], limit + pos)
                if qty > 0:
                    orders.append(Order(product, bid, -qty))
                    pos -= qty

        skew = -(pos / max(1, limit)) * cfg.inv_skew
        buy_px = int(round(fair - cfg.spread + skew))
        sell_px = int(round(fair + cfg.spread + skew))
        if buy_px >= sell_px:
            buy_px, sell_px = int(fair) - 1, int(fair) + 1

        buy_qty = min(cfg.order_size, limit - pos)
        sell_qty = min(cfg.order_size, limit + pos)
        if buy_qty > 0:
            orders.append(Order(product, buy_px, buy_qty))
        if sell_qty > 0:
            orders.append(Order(product, sell_px, -sell_qty))
        return orders

    def _voucher_fair(self, name: str, depth: OrderDepth, S: float) -> Optional[float]:
        K = VEV_STRIKES[name]
        intrinsic = max(S - K, 0.0)
        own_mid = self._mid(depth)
        if own_mid is None:
            return None
        # Smooth only the time-value component; intrinsic moves with S instantly.
        premium = own_mid - intrinsic
        smoothed = self._ema("vev_prem_" + name, premium, alpha=0.05)
        return max(intrinsic, intrinsic + smoothed)

    def run(self, state: TradingState):
        if state.traderData:
            try:
                self._state = json.loads(state.traderData)
            except Exception:
                self._state = {}

        orders: Dict[str, List[Order]] = {}
        depths = state.order_depths

        S: Optional[float] = None
        if UNDERLYING in depths:
            S = self._mid(depths[UNDERLYING])
            if S is not None:
                S = self._ema("velv_ema", S, alpha=0.3)

        for product, depth in depths.items():
            cfg = PRODUCT_CFG.get(product)
            if cfg is None:
                continue
            pos = state.position.get(product, 0)

            if product == UNDERLYING:
                fair = S if S is not None else self._mid(depth)
            elif product == HYDROGEL:
                m = self._mid(depth)
                if m is None:
                    continue
                fair = self._ema("hydro_ema", m, alpha=0.2)
            elif product in VEV_STRIKES:
                if S is None:
                    continue
                fair = self._voucher_fair(product, depth, S)
            else:
                continue

            if fair is None:
                continue
            orders[product] = self._mm(product, depth, pos, fair, cfg)

        trader_data = json.dumps(self._state)
        return orders, 0, trader_data
