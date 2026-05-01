from datamodel import Order, OrderDepth, TradingState
from typing import Dict, List
import json
from statistics import median

POSITION_LIMITS = {
    "ASH_COATED_OSMIUM": 80,
    "INTARIAN_PEPPER_ROOT": 80,
}

PEPPER = "INTARIAN_PEPPER_ROOT"
OSMIUM = "ASH_COATED_OSMIUM"

CFG = {
    PEPPER: {
        "history_len": 45,
        "take_edge": 1,
        "base_size": 24,
        "join_offset": 1,
        "inventory_soft": 0.45,
        "inventory_hard": 0.80,
        "anchor": None,
    },
    OSMIUM: {
        "history_len": 55,
        "take_edge": 2,
        "base_size": 20,
        "join_offset": 1,
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
            if product not in POSITION_LIMITS:
                continue

            orders = self._trade_product(product, order_depth, state, memory)
            result[product] = orders

        trader_data = self._dump_memory(memory)
        conversions = 0
        return result, conversions, trader_data

    def _trade_product(
        self,
        product: str,
        order_depth: OrderDepth,
        state: TradingState,
        memory: dict,
    ) -> List[Order]:
        orders: List[Order] = []

        if not order_depth.buy_orders or not order_depth.sell_orders:
            return orders

        best_bid = max(order_depth.buy_orders.keys())
        best_ask = min(order_depth.sell_orders.keys())
        mid = (best_bid + best_ask) / 2.0
        spread = best_ask - best_bid

        mids = memory.setdefault("mids", {}).setdefault(product, [])
        mids.append(mid)
        keep = CFG[product]["history_len"]
        if len(mids) > keep:
            del mids[:-keep]

        fair = self._fair_value(product, mids)
        fair_int = int(round(fair))

        pos = state.position.get(product, 0)
        limit = POSITION_LIMITS[product]

        buy_cap = max(0, limit - pos)
        sell_cap = max(0, limit + pos)

        take_edge = CFG[product]["take_edge"]

        for ask in sorted(order_depth.sell_orders.keys()):
            if buy_cap <= 0:
                break
            ask_qty = -order_depth.sell_orders[ask]
            if ask_qty <= 0:
                continue

            should_buy = (fair - ask) >= take_edge or (ask <= fair_int and pos < 0)
            if should_buy:
                qty = min(buy_cap, ask_qty)
                if qty > 0:
                    orders.append(Order(product, ask, qty))
                    buy_cap -= qty
                    pos += qty

        for bid in sorted(order_depth.buy_orders.keys(), reverse=True):
            if sell_cap <= 0:
                break
            bid_qty = order_depth.buy_orders[bid]
            if bid_qty <= 0:
                continue

            should_sell = (bid - fair) >= take_edge or (bid >= fair_int and pos > 0)
            if should_sell:
                qty = min(sell_cap, bid_qty)
                if qty > 0:
                    orders.append(Order(product, bid, -qty))
                    sell_cap -= qty
                    pos -= qty

        buy_cap = max(0, limit - pos)
        sell_cap = max(0, limit + pos)

        buy_sz, sell_sz = self._quote_sizes(product, pos, limit, buy_cap, sell_cap)

        if spread <= 2:
            quote_offset = 1
        elif spread <= 6:
            quote_offset = CFG[product]["join_offset"]
        else:
            quote_offset = 2

        bid_quote = min(best_bid + 1, fair_int - quote_offset)
        ask_quote = max(best_ask - 1, fair_int + quote_offset)

        if bid_quote >= ask_quote:
            bid_quote = min(bid_quote, fair_int - 1)
            ask_quote = max(ask_quote, fair_int + 1)

        if pos > 0:
            skew = 1 + int((pos / limit) * 4)
            bid_quote -= skew
            ask_quote -= max(1, skew // 2)
        elif pos < 0:
            skew = 1 + int((-pos / limit) * 4)
            bid_quote += max(1, skew // 2)
            ask_quote += skew

        if buy_sz > 0 and bid_quote < best_ask:
            orders.append(Order(product, bid_quote, buy_sz))

        if sell_sz > 0 and ask_quote > best_bid:
            orders.append(Order(product, ask_quote, -sell_sz))

        return orders

    def _fair_value(self, product: str, mids: List[float]) -> float:
        cfg = CFG[product]

        if product == PEPPER:
            tail = mids[-25:] if len(mids) >= 25 else mids
            return float(median(tail))

        anchor = cfg["anchor"]
        short = mids[-8:] if len(mids) >= 8 else mids
        long = mids[-30:] if len(mids) >= 30 else mids
        short_avg = sum(short) / len(short)
        long_avg = sum(long) / len(long)
        local = 0.65 * short_avg + 0.35 * long_avg
        return 0.55 * anchor + 0.45 * local

    def _quote_sizes(
        self,
        product: str,
        pos: int,
        limit: int,
        buy_cap: int,
        sell_cap: int,
    ):
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

        if abs(pos) <= limit // 10:
            buy_sz = min(max(buy_sz, base), buy_cap)
            sell_sz = min(max(sell_sz, base), sell_cap)

        return buy_sz, sell_sz

    def _load_memory(self, trader_data: str) -> dict:
        if not trader_data:
            return {"mids": {}}
        try:
            memory = json.loads(trader_data)
            if isinstance(memory, dict):
                memory.setdefault("mids", {})
                return memory
        except Exception:
            pass
        return {"mids": {}}

    def _dump_memory(self, memory: dict) -> str:
        try:
            return json.dumps(memory, separators=(",", ":"))
        except Exception:
            return ""
