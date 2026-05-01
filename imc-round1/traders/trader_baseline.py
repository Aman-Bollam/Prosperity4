from datamodel import Order, OrderDepth, TradingState
from typing import Dict, List
import json

PEPPER = "INTARIAN_PEPPER_ROOT"
OSMIUM = "ASH_COATED_OSMIUM"

POSITION_LIMITS = {
    PEPPER: 80,
    OSMIUM: 80,
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
        return []

    def trade_osmium(self, order_depth: OrderDepth, state: TradingState, memory: dict) -> List[Order]:
        return []

    def _load_memory(self, trader_data: str) -> dict:
        if not trader_data:
            return {}
        try:
            out = json.loads(trader_data)
            return out if isinstance(out, dict) else {}
        except Exception:
            return {}

    def _dump_memory(self, memory: dict) -> str:
        try:
            return json.dumps(memory, separators=(",", ":"))
        except Exception:
            return ""
