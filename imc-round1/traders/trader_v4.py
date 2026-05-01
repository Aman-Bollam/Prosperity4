from typing import Dict, List, Optional, Tuple
from datamodel import Order, OrderDepth, TradingState
import json


class Trader:
    POSITION_LIMITS = {
        "INTARIAN_PEPPER_ROOT": 80,
        "ASH_COATED_OSMIUM": 80,
    }

    # How many recent mids to keep for Pepper line-fit
    PEPPER_LINFIT_WINDOW = 35
    PEPPER_HISTORY_LEN = 70

    def __init__(self) -> None:
        self.pepper_anchor: Optional[float] = None
        self.last_mid: Dict[str, Optional[float]] = {
            "INTARIAN_PEPPER_ROOT": None,
            "ASH_COATED_OSMIUM": None,
        }
        self.ema_mid: Dict[str, Optional[float]] = {
            "INTARIAN_PEPPER_ROOT": None,
            "ASH_COATED_OSMIUM": None,
        }
        # History for line-fit fair value (Pepper only)
        self._pepper_times: List[int] = []
        self._pepper_mids: List[float] = []

    # ------------------------------------------------------------------ #
    # State persistence                                                    #
    # ------------------------------------------------------------------ #

    def _load_state(self, trader_data: str) -> None:
        if not trader_data:
            return
        try:
            d = json.loads(trader_data)
            if not isinstance(d, dict):
                return
            self.pepper_anchor = d.get("pa")
            lm = d.get("lm", {})
            for k in self.last_mid:
                if k in lm:
                    self.last_mid[k] = lm[k]
            em = d.get("em", {})
            for k in self.ema_mid:
                if k in em:
                    self.ema_mid[k] = em[k]
            self._pepper_times = d.get("pt", [])
            self._pepper_mids = d.get("pm", [])
        except Exception:
            pass

    def _dump_state(self) -> str:
        d = {
            "pa": self.pepper_anchor,
            "lm": {k: v for k, v in self.last_mid.items() if v is not None},
            "em": {k: v for k, v in self.ema_mid.items() if v is not None},
            "pt": self._pepper_times[-self.PEPPER_HISTORY_LEN:],
            "pm": self._pepper_mids[-self.PEPPER_HISTORY_LEN:],
        }
        return json.dumps(d, separators=(",", ":"))

    # ------------------------------------------------------------------ #
    # Shared book helpers (unchanged from v1)                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def best_bid_ask(order_depth: OrderDepth) -> Tuple[Optional[int], Optional[int]]:
        best_bid = max(order_depth.buy_orders) if order_depth.buy_orders else None
        best_ask = min(order_depth.sell_orders) if order_depth.sell_orders else None
        return best_bid, best_ask

    @staticmethod
    def get_mid(best_bid, best_ask, fallback):
        if best_bid is not None and best_ask is not None:
            return (best_bid + best_ask) / 2
        if best_bid is not None:
            return float(best_bid)
        if best_ask is not None:
            return float(best_ask)
        return fallback

    @staticmethod
    def get_spread(best_bid, best_ask, default):
        if best_bid is None or best_ask is None:
            return default
        return float(best_ask - best_bid)

    @staticmethod
    def level_volume(book, price, is_sell=False):
        if price is None:
            return 0
        vol = book.get(price, 0)
        return abs(vol) if is_sell else vol

    @staticmethod
    def imbalance(order_depth: OrderDepth, level: int = 1) -> float:
        bids = sorted(order_depth.buy_orders.keys(), reverse=True)
        asks = sorted(order_depth.sell_orders.keys())
        if len(bids) < level or len(asks) < level:
            return 0.0
        bid = bids[level - 1]
        ask = asks[level - 1]
        bid_vol = order_depth.buy_orders.get(bid, 0)
        ask_vol = abs(order_depth.sell_orders.get(ask, 0))
        denom = bid_vol + ask_vol
        if denom == 0:
            return 0.0
        return (bid_vol - ask_vol) / denom

    @staticmethod
    def microprice(order_depth, best_bid, best_ask, mid):
        if best_bid is None or best_ask is None:
            return mid
        bid_vol = order_depth.buy_orders.get(best_bid, 0)
        ask_vol = abs(order_depth.sell_orders.get(best_ask, 0))
        denom = bid_vol + ask_vol
        if denom == 0:
            return mid
        return (best_ask * bid_vol + best_bid * ask_vol) / denom

    @staticmethod
    def clamp(x, lo, hi):
        return max(lo, min(hi, x))

    def book_state(self, product: str, order_depth: OrderDepth):
        best_bid, best_ask = self.best_bid_ask(order_depth)
        mid = self.get_mid(best_bid, best_ask, self.last_mid[product])
        if mid is None:
            mid = self.ema_mid[product] if self.ema_mid[product] is not None else 10000.0
        spread = self.get_spread(best_bid, best_ask, 12.0 if product == "INTARIAN_PEPPER_ROOT" else 16.0)
        micro = self.microprice(order_depth, best_bid, best_ask, mid)
        micro_dev = 0.0 if micro is None else micro - mid
        imb1 = self.imbalance(order_depth, 1)
        imb2 = self.imbalance(order_depth, 2)
        imb3 = self.imbalance(order_depth, 3)
        last_mid = self.last_mid[product]
        ret1 = 0.0 if last_mid is None else mid - last_mid

        if self.ema_mid[product] is None:
            self.ema_mid[product] = mid
        else:
            alpha = 0.10 if product == "ASH_COATED_OSMIUM" else 0.06
            self.ema_mid[product] = (1 - alpha) * self.ema_mid[product] + alpha * mid

        self.last_mid[product] = mid
        return best_bid, best_ask, mid, spread, micro_dev, imb1, imb2, imb3, ret1

    # ------------------------------------------------------------------ #
    # Pepper line-fit fair value                                          #
    # ------------------------------------------------------------------ #

    def _pepper_linfit(self) -> Optional[float]:
        xs = self._pepper_times
        ys = self._pepper_mids
        win = self.PEPPER_LINFIT_WINDOW
        if len(xs) < 3:
            return None
        xs = xs[-win:] if len(xs) >= win else xs
        ys = ys[-win:] if len(ys) >= win else ys
        x0 = xs[0]
        xs2 = [x - x0 for x in xs]
        n = len(xs2)
        sum_x = sum(xs2)
        sum_y = sum(ys)
        sum_xx = sum(x * x for x in xs2)
        sum_xy = sum(x * y for x, y in zip(xs2, ys))
        denom = n * sum_xx - sum_x * sum_x
        if denom == 0:
            return ys[-1]
        slope = (n * sum_xy - sum_x * sum_y) / denom
        intercept = (sum_y - slope * sum_x) / n
        return intercept + slope * xs2[-1]

    # ------------------------------------------------------------------ #
    # Signal computation                                                   #
    # ------------------------------------------------------------------ #

    def pepper_signal(self, state: TradingState, order_depth: OrderDepth):
        best_bid, best_ask, mid, spread, micro_dev, imb1, imb2, imb3, ret1 = self.book_state(
            "INTARIAN_PEPPER_ROOT", order_depth
        )

        # Update line-fit history
        self._pepper_times.append(state.timestamp)
        self._pepper_mids.append(mid)
        if len(self._pepper_times) > self.PEPPER_HISTORY_LEN:
            del self._pepper_times[:-self.PEPPER_HISTORY_LEN]
            del self._pepper_mids[:-self.PEPPER_HISTORY_LEN]

        raw_anchor = mid - state.timestamp / 100.0
        if self.pepper_anchor is None:
            self.pepper_anchor = raw_anchor
        else:
            self.pepper_anchor = 0.992 * self.pepper_anchor + 0.008 * raw_anchor

        trend_fair = self.pepper_anchor + state.timestamp / 100.0
        edge = 0.28 + 8.55 * imb1 - 0.06 * imb2 - 1.78 * imb3 - 0.66 * micro_dev - 0.11 * ret1 - 0.015 * spread

        # Blend trend_fair, line-fit, and current mid.
        # Line-fit tracks the intraday slope with only 35-tick warm-up;
        # trend_fair carries the structural long bias across days.
        line_fair = self._pepper_linfit()
        if line_fair is not None:
            fair = 0.45 * trend_fair + 0.30 * line_fair + 0.25 * mid + edge
        else:
            fair = 0.55 * trend_fair + 0.45 * mid + edge

        # Stronger initial long bias (32 vs 28) to better capture upward drift.
        time_bias = int(32 * (1.0 - state.timestamp / 100000.0))
        target = self.clamp(time_bias + int(round(6.0 * edge)), -20, 80)

        return {
            "best_bid": best_bid,
            "best_ask": best_ask,
            "mid": mid,
            "spread": spread,
            "fair": fair,
            "edge": edge,
            "target": target,
        }

    def ash_signal(self, order_depth: OrderDepth):
        best_bid, best_ask, mid, spread, micro_dev, imb1, imb2, imb3, ret1 = self.book_state(
            "ASH_COATED_OSMIUM", order_depth
        )

        dev = mid - 10000.0
        edge = 0.26 + 7.12 * imb1 - 0.09 * imb2 - 0.85 * imb3 - 0.50 * micro_dev - 0.155 * ret1 - 0.0167 * dev - 0.015 * spread
        fair = mid + edge

        target = self.clamp(int(round(-2.1 * dev + 8.0 * imb1 + 2.5 * edge)), -55, 55)

        return {
            "best_bid": best_bid,
            "best_ask": best_ask,
            "mid": mid,
            "spread": spread,
            "fair": fair,
            "edge": edge,
            "target": target,
        }

    # ------------------------------------------------------------------ #
    # Order execution (unchanged from v1)                                 #
    # ------------------------------------------------------------------ #

    def take_orders(self, product, order_depth, fair, position, buy_threshold, sell_threshold, target):
        orders: List[Order] = []
        limit = self.POSITION_LIMITS[product]
        buy_capacity = limit - position
        sell_capacity = limit + position

        if target > position:
            buy_threshold -= 0.35
            sell_threshold += 0.25
        elif target < position:
            sell_threshold -= 0.35
            buy_threshold += 0.25

        for ask in sorted(order_depth.sell_orders):
            if buy_capacity <= 0:
                break
            ask_volume = abs(order_depth.sell_orders[ask])
            if ask <= fair - buy_threshold:
                qty = min(buy_capacity, ask_volume)
                if qty > 0:
                    orders.append(Order(product, int(ask), int(qty)))
                    buy_capacity -= qty

        for bid in sorted(order_depth.buy_orders, reverse=True):
            if sell_capacity <= 0:
                break
            bid_volume = order_depth.buy_orders[bid]
            if bid >= fair + sell_threshold:
                qty = min(sell_capacity, bid_volume)
                if qty > 0:
                    orders.append(Order(product, int(bid), int(-qty)))
                    sell_capacity -= qty

        return orders

    def market_make(self, product, best_bid, best_ask, fair, position, target,
                    base_half_spread, outer_width, size_inner, size_outer):
        orders: List[Order] = []
        limit = self.POSITION_LIMITS[product]

        target_gap = position - target
        reservation = fair - 0.14 * target_gap

        bid_1 = int(round(reservation - base_half_spread))
        ask_1 = int(round(reservation + base_half_spread))
        bid_2 = bid_1 - outer_width
        ask_2 = ask_1 + outer_width

        if best_bid is not None:
            bid_1 = min(bid_1, best_bid + 1)
            bid_2 = min(bid_2, best_bid)
        if best_ask is not None:
            ask_1 = max(ask_1, best_ask - 1)
            ask_2 = max(ask_2, best_ask)

        if ask_1 <= bid_1:
            ask_1 = bid_1 + 1
        if ask_2 <= bid_2:
            ask_2 = bid_2 + 2
        if bid_2 >= bid_1:
            bid_2 = bid_1 - 1
        if ask_2 <= ask_1:
            ask_2 = ask_1 + 1

        buy_capacity = limit - position
        sell_capacity = limit + position

        buy_inner = max(0, min(size_inner, buy_capacity))
        sell_inner = max(0, min(size_inner, sell_capacity))
        buy_outer = max(0, min(size_outer, buy_capacity - buy_inner))
        sell_outer = max(0, min(size_outer, sell_capacity - sell_inner))

        if target > position:
            extra = min(12, buy_capacity - buy_inner)
            buy_inner += max(0, extra)
            sell_inner = max(0, sell_inner - 4)
        elif target < position:
            extra = min(12, sell_capacity - sell_inner)
            sell_inner += max(0, extra)
            buy_inner = max(0, buy_inner - 4)

        if position > 60:
            buy_inner = min(buy_inner, 2)
            buy_outer = 0
            sell_inner = min(sell_capacity, sell_inner + 10)
        elif position < -60:
            sell_inner = min(sell_inner, 2)
            sell_outer = 0
            buy_inner = min(buy_capacity, buy_inner + 10)

        if buy_inner > 0:
            orders.append(Order(product, int(bid_1), int(buy_inner)))
        if sell_inner > 0:
            orders.append(Order(product, int(ask_1), int(-sell_inner)))
        if buy_outer > 0:
            orders.append(Order(product, int(bid_2), int(buy_outer)))
        if sell_outer > 0:
            orders.append(Order(product, int(ask_2), int(-sell_outer)))

        return orders

    # ------------------------------------------------------------------ #
    # Per-product trade methods                                            #
    # ------------------------------------------------------------------ #

    def trade_pepper(self, state: TradingState, order_depth: OrderDepth, position: int) -> List[Order]:
        sig = self.pepper_signal(state, order_depth)
        edge = sig["edge"]
        fair = sig["fair"]
        target = sig["target"]

        buy_threshold = 0.85 if edge > 1.5 else 1.10
        sell_threshold = 1.35 if edge > 1.5 else 1.75
        if edge < -1.0:
            buy_threshold = 1.35
            sell_threshold = 1.00

        orders = self.take_orders(
            "INTARIAN_PEPPER_ROOT", order_depth, fair, position,
            buy_threshold, sell_threshold, target,
        )

        new_position = position + sum(o.quantity for o in orders)
        orders.extend(
            self.market_make(
                "INTARIAN_PEPPER_ROOT",
                sig["best_bid"], sig["best_ask"], fair,
                new_position, target,
                base_half_spread=2,
                outer_width=2,
                size_inner=18,
                size_outer=12,
            )
        )
        return orders

    def trade_ash(self, order_depth: OrderDepth, position: int) -> List[Order]:
        sig = self.ash_signal(order_depth)
        edge = sig["edge"]
        fair = sig["fair"]
        target = sig["target"]

        buy_threshold = 0.50 if edge > 0.5 else 0.85
        sell_threshold = 0.50 if edge < -0.5 else 0.85

        orders = self.take_orders(
            "ASH_COATED_OSMIUM", order_depth, fair, position,
            buy_threshold, sell_threshold, target,
        )

        new_position = position + sum(o.quantity for o in orders)
        orders.extend(
            self.market_make(
                "ASH_COATED_OSMIUM",
                sig["best_bid"], sig["best_ask"], fair,
                new_position, target,
                base_half_spread=3,
                outer_width=3,
                size_inner=12,
                size_outer=8,
            )
        )
        return orders

    # ------------------------------------------------------------------ #
    # Entry point                                                          #
    # ------------------------------------------------------------------ #

    def run(self, state: TradingState):
        self._load_state(state.traderData)

        result: Dict[str, List[Order]] = {}
        for product, order_depth in state.order_depths.items():
            position = state.position.get(product, 0)
            if product == "INTARIAN_PEPPER_ROOT":
                result[product] = self.trade_pepper(state, order_depth, position)
            elif product == "ASH_COATED_OSMIUM":
                result[product] = self.trade_ash(order_depth, position)

        return result, 0, self._dump_state()
