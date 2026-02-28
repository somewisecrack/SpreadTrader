"""
websocket_worker.py – QThread that runs the Shoonya WebSocket listener.

Emits:
  tick_received(token: str, ltp: float)  — on each price update
  connected()                             — WebSocket opened
  disconnected()                          — WebSocket closed
  error_occurred(msg: str)                — on error
  reconnect_needed()                      — requests UI to attempt reconnect
"""
import json
import logging
import time

from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger("SpreadTrader.WSWorker")


class WebSocketWorker(QThread):
    """
    Runs in its own QThread. Receives raw Shoonya WebSocket messages,
    parses the 'lp' (last price) field, and emits tick_received signals
    to the main thread's PnL engine.
    """

    tick_received   = pyqtSignal(str, float)   # token, ltp
    connected       = pyqtSignal()
    disconnected    = pyqtSignal()
    error_occurred  = pyqtSignal(str)
    reconnect_needed= pyqtSignal()

    def __init__(self, shoonya_client, parent=None):
        super().__init__(parent)
        self._client = shoonya_client
        self._running = False
        self._subscriptions: list[tuple[str, str]] = []  # (exchange, token)

    def set_subscriptions(self, exchange_token_pairs: list[tuple[str, str]]):
        """Update subscriptions. Safe to call before or after run()."""
        self._subscriptions = exchange_token_pairs

    # ──────────────────────────────────────────────────────────────
    #   QThread entry point
    # ──────────────────────────────────────────────────────────────

    def run(self):
        self._running = True
        logger.info("WebSocketWorker thread started")

        def _on_open(ws):
            self.connected.emit()
            # Subscribe to all tracked tokens
            if self._subscriptions:
                self._client.subscribe_tokens(self._subscriptions)

        def _on_tick(ws, message):
            self._handle_message(message)

        def _on_error(ws, error):
            self.error_occurred.emit(str(error))

        def _on_close(ws, code, msg):
            self.disconnected.emit()
            if self._running:
                # Brief wait then signal for reconnect
                time.sleep(5)
                self.reconnect_needed.emit()

        self._client.start_websocket(
            on_open=_on_open,
            on_tick=_on_tick,
            on_error=_on_error,
            on_close=_on_close,
        )

    def stop(self):
        self._running = False
        try:
            self._client.close_websocket()
        except Exception:
            pass
        self.quit()

    # ──────────────────────────────────────────────────────────────
    #   Message parser
    # ──────────────────────────────────────────────────────────────

    def _handle_message(self, message):
        """
        Parse a Shoonya WebSocket touchline message.
        Format: {"t":"tf","e":"NSE","tk":"2885","lp":"2500.50", ...}
        """
        try:
            if isinstance(message, str):
                data = json.loads(message)
            elif isinstance(message, dict):
                data = message
            else:
                return

            msg_type = data.get("t", "")
            if msg_type not in ("tf", "tk"):
                # Not a touchline feed message
                return

            token = data.get("tk", "")
            lp_raw = data.get("lp")

            if not token or lp_raw is None:
                return

            ltp = float(lp_raw)
            self.tick_received.emit(token, ltp)

        except (json.JSONDecodeError, ValueError, TypeError):
            pass
        except Exception:
            logger.exception("Unexpected error parsing WebSocket message")
