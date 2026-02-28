"""
pnl_engine.py – Real-time PnL calculation for virtual pairs.

Formula:
    Virtual_PnL = (ltp_A - entry_A) × qty_A + (entry_B - ltp_B) × qty_B

Maintains an in-memory state dict keyed by pair_id.
Thread-safe: only mutates state from the WebSocket QThread via signals.
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("SpreadTrader.PnL")


@dataclass
class PairState:
    pair_id: int
    leg1_sym: str
    leg1_token: str
    leg1_qty: int
    leg2_sym: str
    leg2_token: str
    leg2_qty: int
    entry_price_1: Optional[float] = None
    entry_price_2: Optional[float] = None
    ltp_1: Optional[float] = None
    ltp_2: Optional[float] = None
    status: str = "pending"  # 'pending' | 'active' | 'closed'

    @property
    def pnl(self) -> Optional[float]:
        """Returns virtual PnL if both entry and ltp are available."""
        if (
            self.status != "active"
            or self.entry_price_1 is None
            or self.entry_price_2 is None
            or self.ltp_1 is None
            or self.ltp_2 is None
        ):
            return None
        leg1_pnl = (self.ltp_1 - self.entry_price_1) * self.leg1_qty
        leg2_pnl = (self.entry_price_2 - self.ltp_2) * self.leg2_qty
        return leg1_pnl + leg2_pnl

    @property
    def pnl_display(self) -> str:
        v = self.pnl
        if v is None:
            return "—"
        sign = "+" if v >= 0 else ""
        return f"{sign}{v:,.2f}"


class PnLEngine:
    """
    Central in-memory registry of active pair states.
    Updated by WebSocket ticks via update_tick().
    """

    def __init__(self):
        self._states: dict[int, PairState] = {}

    def load_pairs(self, pairs: list[dict]):
        """
        Initialise (or refresh) pair states from DB rows.
        Existing LTP values are preserved if the pair already exists.
        """
        for p in pairs:
            pid = p["id"]
            if pid in self._states:
                # Refresh mutable fields but keep live LTPs
                existing = self._states[pid]
                existing.entry_price_1 = p.get("entry_price_1")
                existing.entry_price_2 = p.get("entry_price_2")
                existing.status = p.get("status", "pending")
            else:
                self._states[pid] = PairState(
                    pair_id=pid,
                    leg1_sym=p["leg1_sym"],
                    leg1_token=p.get("leg1_token", ""),
                    leg1_qty=p["leg1_qty"],
                    leg2_sym=p["leg2_sym"],
                    leg2_token=p.get("leg2_token", ""),
                    leg2_qty=p["leg2_qty"],
                    entry_price_1=p.get("entry_price_1"),
                    entry_price_2=p.get("entry_price_2"),
                    ltp_1=p.get("ltp_1"),
                    ltp_2=p.get("ltp_2"),
                    status=p.get("status", "pending"),
                )
        logger.info(f"PnLEngine loaded {len(self._states)} pair states")

    def update_tick(self, token: str, ltp: float) -> list[int]:
        """
        Update LTP for all pairs containing this token.
        Returns list of pair_ids whose PnL changed.
        """
        changed = []
        for pid, state in self._states.items():
            if state.status == "closed":
                continue
            updated = False
            if state.leg1_token == token:
                state.ltp_1 = ltp
                updated = True
            if state.leg2_token == token:
                state.ltp_2 = ltp
                updated = True
            if updated:
                changed.append(pid)
        return changed

    def activate_pair(self, pair_id: int, entry_price_1: float, entry_price_2: float):
        """Mark a pair as active with its opening prices."""
        state = self._states.get(pair_id)
        if state:
            state.entry_price_1 = entry_price_1
            state.entry_price_2 = entry_price_2
            state.status = "active"
            logger.info(f"PnLEngine: pair {pair_id} activated e1={entry_price_1} e2={entry_price_2}")

    def close_pair(self, pair_id: int):
        state = self._states.get(pair_id)
        if state:
            state.status = "closed"

    def remove_pair(self, pair_id: int):
        self._states.pop(pair_id, None)

    def get_state(self, pair_id: int) -> Optional[PairState]:
        return self._states.get(pair_id)

    def get_all_states(self) -> list[PairState]:
        return list(self._states.values())

    def get_subscribed_tokens(self) -> set[str]:
        """Return all unique tokens for active/pending pairs."""
        tokens = set()
        for state in self._states.values():
            if state.status != "closed":
                if state.leg1_token:
                    tokens.add(state.leg1_token)
                if state.leg2_token:
                    tokens.add(state.leg2_token)
        return tokens
