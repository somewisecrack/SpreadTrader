"""
shoonya_client.py – Thin wrapper around the Shoonya NorenApi.
Provides get_open_price(), subscribe(), unsubscribe() helpers.
"""
import logging
from typing import Callable, Optional

logger = logging.getLogger("SpreadTrader.ShoonyaClient")


class ShoonyaClient:
    """
    Wraps the authenticated NorenApi object.
    All interactions with the Shoonya API go through here.
    """

    def __init__(self, api):
        """
        :param api: An authenticated NorenApi instance from auth.login_shoonya()
        """
        self._api = api

    # ──────────────────────────────────────────────────────────────
    #   QUOTES
    # ──────────────────────────────────────────────────────────────

    def get_open_price(self, exchange: str, token: str) -> Optional[float]:
        """
        Fetch the opening price for a scrip using get_quotes().
        Returns the 'o' (open) field as a float, or None on error.

        :param exchange: e.g. 'NSE', 'BSE', 'NFO'
        :param token:    Shoonya numeric scrip token (not symbol name)
        """
        try:
            resp = self._api.get_quotes(exchange=exchange, token=token)
            if resp and resp.get("stat") == "Ok":
                raw_open = resp.get("o", None)
                if raw_open is not None:
                    price = float(raw_open)
                    logger.info(f"Open price [{exchange}:{token}] = {price}")
                    return price
                else:
                    logger.warning(f"'o' key missing in get_quotes response for {exchange}:{token}")
            else:
                err = resp.get("emsg", "No error message") if resp else "None response"
                logger.error(f"get_quotes failed for {exchange}:{token}: {err}")
        except Exception:
            logger.exception(f"Exception in get_open_price({exchange}, {token})")
        return None

    def get_ltp(self, exchange: str, token: str) -> Optional[float]:
        """
        Fetch the current last traded price (lp) via get_quotes().
        Used as a fallback when WebSocket is not connected.
        """
        try:
            resp = self._api.get_quotes(exchange=exchange, token=token)
            if resp and resp.get("stat") == "Ok":
                raw_ltp = resp.get("lp", resp.get("c", None))
                if raw_ltp is not None:
                    return float(raw_ltp)
        except Exception:
            logger.exception(f"Exception in get_ltp({exchange}, {token})")
        return None

    def search_scrip(self, exchange: str, searchtext: str) -> list[dict]:
        """
        Search for a scrip token by symbol name.
        Returns a list of matching scrip dicts with 'token', 'tsym', 'cname'.
        """
        try:
            resp = self._api.searchscrip(exchange=exchange, searchtext=searchtext)
            if resp and resp.get("stat") == "Ok":
                return resp.get("values", [])
            logger.warning(f"searchscrip returned no results for '{searchtext}' on {exchange}")
        except Exception:
            logger.exception(f"Exception in search_scrip({exchange}, {searchtext})")
        return []

    # ──────────────────────────────────────────────────────────────
    #   WEBSOCKET
    # ──────────────────────────────────────────────────────────────

    def start_websocket(
        self,
        on_open: Callable,
        on_tick: Callable,
        on_error: Callable,
        on_close: Callable,
    ):
        """
        Open the Shoonya WebSocket.  Callbacks follow NorenApi spec.
        """
        # Fix for macOS PyInstaller bundle: SSL certs may not be available
        import ssl
        import websocket as _ws
        _ws.enableTrace(False)
        # Allow self-signed / unavailable cert chains inside frozen bundle
        _orig_create = ssl.create_default_context
        def _patched_ssl(*args, **kwargs):
            ctx = _orig_create(*args, **kwargs)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return ctx
        ssl.create_default_context = _patched_ssl

        # NorenApi calls these with varying signatures across versions — use *args
        def _on_open(*args):
            logger.info("WebSocket connected")
            on_open(args[0] if args else None)

        def _on_message(*args):
            # args may be (ws, message) or just (message,)
            msg = args[-1] if args else None
            on_tick(args[0] if len(args) > 1 else None, msg)

        def _on_error(*args):
            err = args[-1] if args else "unknown error"
            logger.error(f"WebSocket error: {err}")
            on_error(args[0] if len(args) > 1 else None, err)

        def _on_close(*args):
            # args: (ws,) or (ws, code, msg) depending on version
            code = args[1] if len(args) > 1 else None
            msg  = args[2] if len(args) > 2 else None
            logger.warning(f"WebSocket closed: {code} {msg}")
            on_close(args[0] if args else None, code, msg)

        self._api.start_websocket(
            order_update_callback=lambda *a: None,
            subscribe_callback=_on_message,
            socket_open_callback=_on_open,
            socket_error_callback=_on_error,
            socket_close_callback=_on_close,
        )


    def subscribe_tokens(self, exchange_token_pairs: list[tuple[str, str]]):
        """
        Subscribe to a list of (exchange, token) pairs for live feed.
        Uses NorenApi touchline subscription.
        """
        if not exchange_token_pairs:
            return
        scrip_list = [f"{ex}|{tok}" for ex, tok in exchange_token_pairs]
        self._api.subscribe(scrip_list)
        logger.info(f"Subscribed to: {scrip_list}")

    def unsubscribe_tokens(self, exchange_token_pairs: list[tuple[str, str]]):
        if not exchange_token_pairs:
            return
        scrip_list = [f"{ex}|{tok}" for ex, tok in exchange_token_pairs]
        self._api.unsubscribe(scrip_list)
        logger.info(f"Unsubscribed from: {scrip_list}")

    def close_websocket(self):
        try:
            self._api.close_websocket()
            logger.info("WebSocket closed cleanly")
        except Exception:
            pass
