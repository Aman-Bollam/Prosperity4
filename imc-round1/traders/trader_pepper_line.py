from datamodel import Order, OrderDepth, TradingState
from typing import Dict, List
import json

POSITION_LIMITS = {
    "INTARIAN_PEPPER_ROOT": 80,
}

PEPPER = "INTARIAN_PEPPER_ROOT"

CFG = {
    "history_len": 60,
    "line_window": 30,
    "take_edge": 1,
    "base_size": 24,
    "inventory_soft": 0.45,
    "inventory_hard": 0.80,
    "quote_offset": 2,
}


class Trader:
    def run(self, state: TradingState):
        memory = self._load_memory(state.traderData)
        result: Dict[str, List[Order]] = {}

        if PEPPER in state.order_depths:
            result[PEPPER] = self.trade_pepper(state.order_depths[PEPPER], state, memory)

        return result, 0, self._dump_memory(memory)

    def trade_pepper(self, order_depth: OrderDepth, state: TradingState, memory: dict) -> List[Order]:
        orders: List[Order] = []
        if not order_depth.buy_orders or not order_depth.sell_orders:
            return orders

        best_bid = max(order_depth.buy_orders)
        best_ask = min(order_depth.sell_orders)
        mid = (best_bid + best_ask) / 2.0

        times = memory.setdefault("times", {}).setdefault(PEPPER, [])
        mids = memory.setdefault("mids", {}).setdefault(PEPPER, [])
        times.append(state.timestamp)
        mids.append(mid)
        keep = CFG["history_len"]
        if len(times) > keep:
            del times[:-keep]
            del mids[:-keep]

        fair = self._line_fair(times, mids)
        fair_int = int(round(fair))

        pos = state.position.get(PEPPER, 0)
        limit = POSITION_LIMITS[PEPPER]
        buy_cap = max(0, limit - pos)
        sell_cap = max(0, limit + pos)

        for ask in sorted(order_depth.sell_orders):
            if buy_cap <= 0:
                break
            ask_qty = -order_depth.sell_orders[ask]
            if ask_qty <= 0:
                continue
            if fair - ask >= CFG["take_edge"] or (ask <= fair_int and pos < 0):
                qty = min(buy_cap, ask_qty)
                if qty > 0:
                    orders.append(Order(PEPPER, ask, qty))
                    pos += qty
                    buy_cap -= qty

        for bid in sorted(order_depth.buy_orders, reverse=True):
            if sell_cap <= 0:
                break
            bid_qty = order_depth.buy_orders[bid]
            if bid_qty <= 0:
                continue
            if bid - fair >= CFG["take_edge"] or (bid >= fair_int and pos > 0):
                qty = min(sell_cap, bid_qty)
                if qty > 0:
                    orders.append(Order(PEPPER, bid, -qty))
                    pos -= qty
                    sell_cap -= qty

        buy_cap = max(0, limit - pos)
        sell_cap = max(0, limit + pos)
        buy_sz, sell_sz = self._quote_sizes(pos, limit, buy_cap, sell_cap)

        offset = 1 if (best_ask - best_bid) <= 8 else CFG["quote_offset"]
        bid_quote = min(best_bid + 1, fair_int - offset)
        ask_quote = max(best_ask - 1, fair_int + offset)

        if pos > 0:
            bid_quote -= 1 + int(4 * pos / limit)
            ask_quote -= 1
        elif pos < 0:
            bid_quote += 1
            ask_quote += 1 + int(4 * (-pos) / limit)

        if buy_sz > 0 and bid_quote < best_ask:
            orders.append(Order(PEPPER, bid_quote, buy_sz))
        if sell_sz > 0 and ask_quote > best_bid:
            orders.append(Order(PEPPER, ask_quote, -sell_sz))

        return orders

    def _line_fair(self, times: List[int], mids: List[float]) -> float:
        if len(mids) < 3:
            return mids[-1]
        win = CFG["line_window"]
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

    def _quote_sizes(self, pos: int, limit: int, buy_cap: int, sell_cap: int):
        base = CFG["base_size"]
        soft = int(limit * CFG["inventory_soft"])
        hard = int(limit * CFG["inventory_hard"])

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
