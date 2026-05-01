from datamodel import Order, OrderDepth, TradingState
from typing import Dict, List, Tuple
import json

POSITION_LIMITS = {
    "ASH_COATED_OSMIUM": 80,
    "INTARIAN_PEPPER_ROOT": 80,
}

PEPPER = "INTARIAN_PEPPER_ROOT"
OSMIUM = "ASH_COATED_OSMIUM"

CFG = {
    PEPPER: {
        "history_len": 70,
        "line_window": 35,
        "take_edge": 1,
        "base_size": 24,
        "quote_offset_tight": 1,
        "quote_offset_wide": 2,
        "inventory_soft": 0.45,
        "inventory_hard": 0.80,
    },
    OSMIUM: {
        "history_len": 260,
        "short_window": 20,
        "long_window": 80,
        "drift_threshold": 1.2,
        "take_edge": 2,
        "base_size": 20,
        "quote_offset_tight": 1,
        "quote_offset_wide": 2,
        "inventory_soft": 0.40,
        "inventory_hard": 0.75,
        "anchor": 10000.0,
    },
}


class Trader:
    def run(self, state: TradingState):
        memory = self._load_memory(state.traderData)
        result: Dict[str, List[Order]] = {}

        for product, order_depth in state.order_depths.items():
            if product == PEPPER:
                result[product] = self.trade_pepper(order_depth, state, memory)
            elif product == OSMIUM:
                result[product] = self.trade_osmium(order_depth, state, memory)

        return result, 0, self._dump_memory(memory)

    def trade_pepper(self, order_depth: OrderDepth, state: TradingState, memory: dict) -> List[Order]:
        if not order_depth.buy_orders or not order_depth.sell_orders:
            return []

        best_bid, best_ask, mid, spread = self._book(order_depth)
        times = memory.setdefault("times", {}).setdefault(PEPPER, [])
        mids = memory.setdefault("mids", {}).setdefault(PEPPER, [])
        times.append(state.timestamp)
        mids.append(mid)
        self._trim(times, mids, CFG[PEPPER]["history_len"])

        fair = self._pepper_fair(times, mids)
        fair_int = int(round(fair))

        pos = state.position.get(PEPPER, 0)
        limit = POSITION_LIMITS[PEPPER]
        orders: List[Order] = []

        buy_cap = max(0, limit - pos)
        sell_cap = max(0, limit + pos)

        buy_cap, sell_cap, pos = self._take_crossed_orders(
            PEPPER,
            order_depth,
            fair,
            fair_int,
            pos,
            buy_cap,
            sell_cap,
            CFG[PEPPER]["take_edge"],
            orders,
        )

        buy_sz, sell_sz = self._quote_sizes(
            PEPPER, pos, limit, max(0, limit - pos), max(0, limit + pos)
        )

        offset = CFG[PEPPER]["quote_offset_tight"] if spread <= 8 else CFG[PEPPER]["quote_offset_wide"]
        bid_quote = min(best_bid + 1, fair_int - offset)
        ask_quote = max(best_ask - 1, fair_int + offset)
        bid_quote, ask_quote = self._skew_quotes(bid_quote, ask_quote, pos, limit)

        if buy_sz > 0 and bid_quote < best_ask:
            orders.append(Order(PEPPER, bid_quote, buy_sz))
        if sell_sz > 0 and ask_quote > best_bid:
            orders.append(Order(PEPPER, ask_quote, -sell_sz))
        return orders

    def trade_osmium(self, order_depth: OrderDepth, state: TradingState, memory: dict) -> List[Order]:
        if not order_depth.buy_orders or not order_depth.sell_orders:
            return []

        best_bid, best_ask, mid, spread = self._book(order_depth)
        mids = memory.setdefault("mids", {}).setdefault(OSMIUM, [])
        mids.append(mid)
        if len(mids) > CFG[OSMIUM]["history_len"]:
            del mids[:-CFG[OSMIUM]["history_len"]]

        fair, regime = self._osmium_fair_and_regime(mids)
        fair_int = int(round(fair))

        pos = state.position.get(OSMIUM, 0)
        limit = POSITION_LIMITS[OSMIUM]
        orders: List[Order] = []

        buy_cap = max(0, limit - pos)
        sell_cap = max(0, limit + pos)

        buy_side_on = True
        sell_side_on = True
        if regime > 0:
            sell_side_on = False
        elif regime < 0:
            buy_side_on = False

        if abs(pos) >= int(limit * 0.65):
            buy_side_on = True
            sell_side_on = True

        buy_cap, sell_cap, pos = self._take_crossed_orders(
            OSMIUM,
            order_depth,
            fair,
            fair_int,
            pos,
            buy_cap,
            sell_cap,
            CFG[OSMIUM]["take_edge"],
            orders,
            buy_side_on=buy_side_on,
            sell_side_on=sell_side_on,
        )

        buy_sz, sell_sz = self._quote_sizes(
            OSMIUM, pos, limit, max(0, limit - pos), max(0, limit + pos)
        )

        offset = CFG[OSMIUM]["quote_offset_tight"] if spread <= 8 else CFG[OSMIUM]["quote_offset_wide"]
        bid_quote = min(best_bid + 1, fair_int - offset)
        ask_quote = max(best_ask - 1, fair_int + offset)

        if regime > 0:
            bid_quote += 1
        elif regime < 0:
            ask_quote -= 1

        bid_quote, ask_quote = self._skew_quotes(bid_quote, ask_quote, pos, limit)

        if buy_side_on and buy_sz > 0 and bid_quote < best_ask:
            orders.append(Order(OSMIUM, bid_quote, buy_sz))
        if sell_side_on and sell_sz > 0 and ask_quote > best_bid:
            orders.append(Order(OSMIUM, ask_quote, -sell_sz))
        return orders

    def _book(self, order_depth: OrderDepth) -> Tuple[int, int, float, int]:
        best_bid = max(order_depth.buy_orders)
        best_ask = min(order_depth.sell_orders)
        mid = (best_bid + best_ask) / 2.0
        spread = best_ask - best_bid
        return best_bid, best_ask, mid, spread

    def _take_crossed_orders(
        self,
        product: str,
        order_depth: OrderDepth,
        fair: float,
        fair_int: int,
        pos: int,
        buy_cap: int,
        sell_cap: int,
        take_edge: int,
        orders: List[Order],
        buy_side_on: bool = True,
        sell_side_on: bool = True,
    ):
        if buy_side_on:
            for ask in sorted(order_depth.sell_orders):
                if buy_cap <= 0:
                    break
                ask_qty = -order_depth.sell_orders[ask]
                if ask_qty <= 0:
                    continue
                if fair - ask >= take_edge or (ask <= fair_int and pos < 0):
                    qty = min(buy_cap, ask_qty)
                    if qty > 0:
                        orders.append(Order(product, ask, qty))
                        pos += qty
                        buy_cap -= qty

        if sell_side_on:
            for bid in sorted(order_depth.buy_orders, reverse=True):
                if sell_cap <= 0:
                    break
                bid_qty = order_depth.buy_orders[bid]
                if bid_qty <= 0:
                    continue
                if bid - fair >= take_edge or (bid >= fair_int and pos > 0):
                    qty = min(sell_cap, bid_qty)
                    if qty > 0:
                        orders.append(Order(product, bid, -qty))
                        pos -= qty
                        sell_cap -= qty

        return buy_cap, sell_cap, pos

    def _pepper_fair(self, times: List[int], mids: List[float]) -> float:
        if len(mids) < 3:
            return mids[-1]
        win = CFG[PEPPER]["line_window"]
        xs = times[-win:] if len(times) >= win else times
        ys = mids[-win:] if len(mids) >= win else mids
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

    def _osmium_fair_and_regime(self, mids: List[float]):
        if not mids:
            return CFG[OSMIUM]["anchor"], 0
        short = mids[-CFG[OSMIUM]["short_window"]:] if len(mids) >= CFG[OSMIUM]["short_window"] else mids
        long = mids[-CFG[OSMIUM]["long_window"]:] if len(mids) >= CFG[OSMIUM]["long_window"] else mids
        short_avg = sum(short) / len(short)
        long_avg = sum(long) / len(long)

        anchor = CFG[OSMIUM]["anchor"]
        fair = 0.55 * anchor + 0.45 * short_avg

        diff = short_avg - long_avg
        if diff > CFG[OSMIUM]["drift_threshold"]:
            regime = 1
        elif diff < -CFG[OSMIUM]["drift_threshold"]:
            regime = -1
        else:
            regime = 0
        return fair, regime

    def _quote_sizes(self, product: str, pos: int, limit: int, buy_cap: int, sell_cap: int):
        cfg = CFG[product]
        base = cfg["base_size"]
        soft = int(limit * cfg["inventory_soft"])
        hard = int(limit * cfg["inventory_hard"])

        buy_sz = min(base, buy_cap)
        sell_sz = min(base, sell_cap)

        if pos >= hard:
            buy_sz = 0
        elif pos >= soft:
            buy_sz = min(buy_sz, max(0, buy_cap // 4))

        if pos <= -hard:
            sell_sz = 0
        elif pos <= -soft:
            sell_sz = min(sell_sz, max(0, sell_cap // 4))

        return buy_sz, sell_sz

    def _skew_quotes(self, bid_quote: int, ask_quote: int, pos: int, limit: int):
        if pos > 0:
            skew = 1 + int((pos / limit) * 4)
            bid_quote -= skew
            ask_quote -= max(1, skew // 2)
        elif pos < 0:
            skew = 1 + int((-pos / limit) * 4)
            bid_quote += max(1, skew // 2)
            ask_quote += skew
        if bid_quote >= ask_quote:
            bid_quote = ask_quote - 1
        return bid_quote, ask_quote

    def _trim(self, xs: List[int], ys: List[float], keep: int):
        if len(xs) > keep:
            del xs[:-keep]
            del ys[:-keep]

    def _load_memory(self, trader_data: str) -> dict:
        if not trader_data:
            return {"times": {}, "mids": {}}
        try:
            out = json.loads(trader_data)
            if isinstance(out, dict):
                out.setdefault("times", {})
                out.setdefault("mids", {})
                return out
        except Exception:
            pass
        return {"times": {}, "mids": {}}

    def _dump_memory(self, memory: dict) -> str:
        return json.dumps(memory, separators=(",", ":"))
