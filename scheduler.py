"""
scheduler.py – IST-aware market event scheduler using QTimer.

Fires signals at precise IST times:
  - 09:15 IST → open_price_trigger (fetch opening prices for pending pairs)
  - 15:35 IST → eod_export_trigger  (write daily CSV)

All time comparisons are done in Asia/Kolkata timezone.
"""
import logging
from datetime import datetime, time as dtime

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

logger = logging.getLogger("SpreadTrader.Scheduler")

try:
    import pytz
    IST = pytz.timezone("Asia/Kolkata")
except ImportError:
    IST = None
    logger.warning("pytz not installed; scheduler will fall back to UTC")


def _now_ist() -> datetime:
    if IST:
        return datetime.now(IST)
    return datetime.utcnow()


class MarketScheduler(QObject):
    """
    Uses a 1-second QTimer to poll the current IST time and fire
    one-shot signals when market milestones are reached.
    """

    # Emitted at 09:15 IST (or whenever the market opens)
    open_price_trigger = pyqtSignal()

    # Emitted at 15:15 IST to automatically close all active positions
    auto_square_off_trigger = pyqtSignal()

    # Emitted at 15:35 IST for end-of-day CSV export
    eod_export_trigger = pyqtSignal()

    # Emitted when the clock minute changes (0-59)
    minute_trigger = pyqtSignal()

    # Emitted every second with IST datetime (used to drive the toolbar clock)
    tick = pyqtSignal(datetime)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fired_open = False
        self._fired_sqoff = False
        self._fired_eod = False
        self._last_minute = -1
        self._timer = QTimer(self)
        self._timer.setInterval(1000)  # 1 second
        self._timer.timeout.connect(self._check)

    def start(self):
        self._timer.start()
        logger.info("MarketScheduler started")

    def stop(self):
        self._timer.stop()
        logger.info("MarketScheduler stopped")

    def reset_daily_flags(self):
        """Call at startup or after midnight to allow re-firing on the next day."""
        self._fired_open = False
        self._fired_sqoff = False
        self._fired_eod = False
        logger.info("Scheduler daily flags reset")

    def _check(self):
        now = _now_ist()
        self.tick.emit(now)

        if now.minute != self._last_minute:
            self._last_minute = now.minute
            self.minute_trigger.emit()

        # Reset at midnight
        if now.hour == 0 and now.minute == 0 and now.second < 5:
            self.reset_daily_flags()

        # 09:15:00 IST trigger
        if (
            not self._fired_open
            and now.hour == 9
            and now.minute == 15
            and now.second == 0
        ):
            self._fired_open = True
            logger.info("09:15 IST → open_price_trigger fired")
            self.open_price_trigger.emit()

        # 15:15:00 IST trigger - Auto Square-off
        if (
            not self._fired_sqoff
            and now.hour == 15
            and now.minute == 15
            and now.second == 0
        ):
            self._fired_sqoff = True
            logger.info("15:15 IST → auto_square_off_trigger fired")
            self.auto_square_off_trigger.emit()

        # 15:35:00 IST trigger
        if (
            not self._fired_eod
            and now.hour == 15
            and now.minute == 35
            and now.second == 0
        ):
            self._fired_eod = True
            logger.info("15:35 IST → eod_export_trigger fired")
            self.eod_export_trigger.emit()
