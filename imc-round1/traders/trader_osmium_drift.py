from datamodel import Order, OrderDepth, TradingState
from typing import Dict, List
import json

POSITION_LIMITS = {
    "ASH_COATED_OSMIUM": 80,
}

OSMIUM = "ASH_COATED_OSMIUM"

CFG = {
    "history_len": 260,
    "short_window": 20,
    "long_window": 80,
    "take_edge": 2,
    "drift_threshold": 1.2,
    "base_size": 20,
    "quote_offset": 2,
    "inventory_soft": 0.40,
    "inventory_hard": 0.75,
}


class Trader:
    def run(self, state: TradingState):
        memory = self._load_memory(state.traderData)
        result: Dict[str, List[Order]] = {}

        if OSMIUM in state.order_depths:
            result[OSMIUM] = self.trade_osmium(state.order_depths[OSMIUM], state, memory)

        return result, 0, self._dump_memory(memory)

    def trade_osmium(self, order_depth: OrderDepth, state: TradingState, memory: dict) -> List[Order]:
        orders: List[Order] = []
        if not order_depth.buy_orders or not order_depth.sell_orders:
            return orders

        best_bid = max(order_depth.buy_orders)
        best_ask = min(order_depth.sell_orders)
        mid = (best_bid + best_ask) / 2.0
        spread = best_ask - best_bid

        mids = memory.setdefault("mids", {}).setdefault(OSMIUM, [])
        mids.append(mid)
        if len(mids) > CFG["history_len"]:
            del mids[:-CFG["history_len"]]

        fair, regime = self._fair_and_regime(mids)
        fair_int = int(round(fair))

        pos = state.position.get(OSMIUM, 0)
        limit = POSITION_LIMITS[OSMIUM]
        buy_cap = max(0, limit - pos)
        sell_cap = max(0, limit + pos)

        # Regime: 1 = updrift, -1 = downdrift, 0 = neutral.
        buy_side_on = True
        sell_side_on = True
        if regime > 0:
            sell_side_on = False
        elif regime < 0:
            buy_side_on = False

        # Override if inventory is too large.
        if abs(pos) >= int(limit * 0.65):
            buy_side_on = True
            sell_side_on = True

        if buy_side_on:
            for ask in sorted(order_depth.sell_orders):
                if buy_cap <= 0:
                    break
                ask_qty = -order_depth.sell_orders[ask]
                if ask_qty <= 0:
                    continue
                if fair - ask >= CFG["take_edge"] or (ask <= fair_int and pos < 0):
                    qty = min(buy_cap, ask_qty)
                    if qty > 0:
                        orders.append(Order(OSMIUM, ask, qty))
                        pos += qty
                        buy_cap -= qty

        if sell_side_on:
            for bid in sorted(order_depth.buy_orders, reverse=True):
                if sell_cap <= 0:
                    break
                bid_qty = order_depth.buy_orders[bid]
                if bid_qty <= 0:
                    continue
                if bid - fair >= CFG["take_edge"] or (bid >= fair_int and pos > 0):
                    qty = min(sell_cap, bid_qty)
                    if qty > 0:
                        orders.append(Order(OSMIUM, bid, -qty))
                        pos -= qty
                        sell_cap -= qty

        buy_cap = max(0, limit - pos)
        sell_cap = max(0, limit + pos)
        buy_sz, sell_sz = self._quote_sizes(pos, limit, buy_cap, sell_cap)

        offset = 1 if spread <= 8 else CFG["quote_offset"]
        bid_quote = min(best_bid + 1, fair_int - offset)
        ask_quote = max(best_ask - 1, fair_int + offset)

        if regime > 0:
            bid_quote += 1
        elif regime < 0:
            ask_quote -= 1

        if pos > 0:
            bid_quote -= 1 + int(4 * pos / limit)
            ask_quote -= 1
        elif pos < 0:
            bid_quote += 1
            ask_quote += 1 + int(4 * (-pos) / limit)

        if buy_side_on and buy_sz > 0 and bid_quote < best_ask:
            orders.append(Order(OSMIUM, bid_quote, buy_sz))
        if sell_side_on and sell_sz > 0 and ask_quote > best_bid:
            orders.append(Order(OSMIUM, ask_quote, -sell_sz))

        return orders

    def _fair_and_regime(self, mids: List[float]):
        if not mids:
            return 10000.0, 0
        short = mids[-CFG["short_window"]:] if len(mids) >= CFG["short_window"] else mids
        long = mids[-CFG["long_window"]:] if len(mids) >= CFG["long_window"] else mids
        short_avg = sum(short) / len(short)
        long_avg = sum(long) / len(long)
        fair = 0.50 * 10000.0 + 0.50 * short_avg

        diff = short_avg - long_avg
        if diff > CFG["drift_threshold"]:
            regime = 1
        elif diff < -CFG["drift_threshold"]:
            regime = -1
        else:
            regime = 0
        return fair, regime

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
            return {"mids": {}}
        try:
            out = json.loads(trader_data)
            if isinstance(out, dict):
                out.setdefault("mids", {})
                return out
        except Exception:
            pass
        return {"mids": {}}

    def _dump_memory(self, memory: dict) -> str:
        return json.dumps(memory, separators=(",", ":"))
