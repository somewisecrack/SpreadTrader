"""
main_window.py – QMainWindow orchestrator for SpreadTrader.

Responsibilities:
  - Toolbar with IST clock, login status, "Add Pair" button
  - Tab widget: Dashboard | History
  - Login on startup (async via QThread mock for responsiveness)
  - Connects Scheduler → 9:15 open price execution
  - Connects Scheduler → 15:35 CSV export
  - Connects WebSocketWorker → DashboardTab PnL updates
  - Handles daily reconnect if WebSocket drops
"""
import csv
import logging
import os
import sys
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QAction, QColor, QFont, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QWidget,
)

from db import DatabaseManager
from pnl_engine import PnLEngine
from scheduler import MarketScheduler
from add_pair_dialog import AddPairDialog
from dashboard_tab import DashboardTab
from history_tab import HistoryTab

logger = logging.getLogger("SpreadTrader.MainWindow")

try:
    import pytz
    IST = pytz.timezone("Asia/Kolkata")
except ImportError:
    IST = None

APP_TITLE = "SpreadTrader  —  Virtual Pairs Desk"
VERSION = "1.0.0"


def _now_ist():
    if IST:
        return datetime.now(IST)
    return datetime.utcnow()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setMinimumSize(1200, 700)

        self._db = DatabaseManager()
        self._engine = PnLEngine()
        self._api = None
        self._client = None
        self._ws_worker = None

        self._build_ui()
        self._apply_dark_theme()
        self._start_scheduler()

        # Attempt login shortly after UI is drawn
        QTimer.singleShot(500, self._attempt_login)

    # ──────────────────────────────────────────────────────────────
    #   UI
    # ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Toolbar ──
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        toolbar.setStyleSheet(
            "QToolBar { background: #0f172a; border-bottom: 1px solid #1e293b; spacing: 8px; padding: 4px 12px; }"
        )
        self.addToolBar(toolbar)

        # App name
        app_label = QLabel(f"  📈 SpreadTrader  v{VERSION}")
        app_label.setStyleSheet("font-size: 15px; font-weight: bold; color: #38bdf8; font-family: 'Segoe UI';")
        toolbar.addWidget(app_label)

        toolbar.addSeparator()

        # Login status
        self._login_status = QLabel("⬤  Not Connected")
        self._login_status.setStyleSheet("color: #ef4444; font-size: 12px;")
        toolbar.addWidget(self._login_status)

        toolbar.addSeparator()

        # Add Pair button
        add_btn = QPushButton("＋  Add Pair")
        add_btn.setStyleSheet(
            "QPushButton { background: #0ea5e9; color: white; border-radius: 6px;"
            " padding: 5px 16px; font-size: 12px; font-weight: bold; }"
            " QPushButton:hover { background: #38bdf8; }"
        )
        add_btn.clicked.connect(self._on_add_pair)
        toolbar.addWidget(add_btn)

        # Stretch
        spacer = QWidget()
        spacer.setSizePolicy(
            spacer.sizePolicy().horizontalPolicy(),
            spacer.sizePolicy().verticalPolicy(),
        )
        from PyQt6.QtWidgets import QSizePolicy
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        # IST Clock
        self._clock_label = QLabel("IST: —")
        self._clock_label.setStyleSheet("font-size: 12px; color: #94a3b8; font-family: 'Consolas';")
        toolbar.addWidget(self._clock_label)

        # ── Tabs ──
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(
            """
            QTabWidget::pane { border: none; background: #0f172a; }
            QTabBar::tab { background: #1e293b; color: #94a3b8; padding: 8px 20px;
                           border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; }
            QTabBar::tab:selected { background: #0f172a; color: #e2e8f0; border-bottom: 2px solid #0ea5e9; }
            QTabBar::tab:hover { background: #334155; }
            """
        )

        self._dashboard = DashboardTab(self._db, self._engine)
        self._history = HistoryTab(self._db)
        self._tabs.addTab(self._dashboard, "📊  Live Dashboard")
        self._tabs.addTab(self._history, "🗂  Trade History")
        self.setCentralWidget(self._tabs)

        # ── Status bar ──
        self._status_bar = self.statusBar()
        self._status_bar.setStyleSheet("QStatusBar { background: #0f172a; color: #475569; font-size: 11px; }")
        self._status_bar.showMessage("Starting up…")

    def _apply_dark_theme(self):
        self.setStyleSheet(
            """
            QMainWindow { background: #0f172a; }
            QWidget { background: #0f172a; color: #e2e8f0; font-family: 'Segoe UI', sans-serif; }
            QMessageBox { background: #1e293b; color: #e2e8f0; }
            QPushButton { font-family: 'Segoe UI'; }
            QLineEdit { font-family: 'Segoe UI'; }
            QComboBox { background: #1e293b; color: #e2e8f0; border: 1px solid #334155;
                        border-radius: 5px; padding: 3px 8px; }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView { background: #1e293b; color: #e2e8f0;
                                          selection-background-color: #1e3a5f; }
            QGroupBox { border: 1px solid #334155; border-radius: 8px; margin-top: 10px; padding-top: 8px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; color: #94a3b8; }
            QDialogButtonBox QPushButton { background: #1e40af; color: white; border-radius: 6px;
                                           padding: 5px 16px; min-width: 80px; }
            QDialogButtonBox QPushButton:hover { background: #1d4ed8; }
            QMessageBox QPushButton { background: #1e40af; color: white; border-radius: 6px;
                                      padding: 5px 16px; min-width: 80px; }
            """
        )

    # ──────────────────────────────────────────────────────────────
    #   Scheduler
    # ──────────────────────────────────────────────────────────────

    def _start_scheduler(self):
        self._scheduler = MarketScheduler(self)
        self._scheduler.tick.connect(self._on_scheduler_tick)
        self._scheduler.open_price_trigger.connect(self._on_open_price_trigger)
        self._scheduler.eod_export_trigger.connect(self._on_eod_export)
        self._scheduler.start()
        logger.info("Scheduler started")

    @pyqtSlot(datetime)
    def _on_scheduler_tick(self, now: datetime):
        ist_str = now.strftime("%H:%M:%S  IST  %d-%b-%Y")
        self._clock_label.setText(f"IST: {ist_str}")

    # ──────────────────────────────────────────────────────────────
    #   Login
    # ──────────────────────────────────────────────────────────────

    def _attempt_login(self):
        self._status_bar.showMessage("Connecting to Shoonya…")
        self._login_status.setText("⬤  Connecting…")
        self._login_status.setStyleSheet("color: #f59e0b; font-size: 12px;")

        try:
            from auth import login_shoonya
            from shoonya_client import ShoonyaClient

            api, err = login_shoonya()
            if err:
                self._login_status.setText(f"⬤  Login Failed")
                self._login_status.setStyleSheet("color: #ef4444; font-size: 12px;")
                self._status_bar.showMessage(f"Login error: {err}")
                logger.error(f"Login failed: {err}")
                return

            self._api = api
            self._client = ShoonyaClient(api)
            self._dashboard.set_client(self._client)

            self._login_status.setText("⬤  Connected")
            self._login_status.setStyleSheet("color: #4ade80; font-size: 12px;")
            self._status_bar.showMessage("Shoonya connected. WebSocket starting…")
            logger.info("Login successful, starting WebSocket")

            self._start_websocket()

        except Exception as e:
            self._login_status.setText("⬤  Error")
            self._login_status.setStyleSheet("color: #ef4444; font-size: 12px;")
            self._status_bar.showMessage(f"Login exception: {e}")
            logger.exception("Exception during login")

    # ──────────────────────────────────────────────────────────────
    #   WebSocket
    # ──────────────────────────────────────────────────────────────

    def _start_websocket(self):
        if not self._client:
            return
        from websocket_worker import WebSocketWorker

        # Build subscription list from all active/pending pairs
        pairs = self._db.get_active_pairs()
        subs = []
        for p in pairs:
            if p.get("leg1_token"):
                subs.append((p["exchange1"], p["leg1_token"]))
            if p.get("leg2_token"):
                subs.append((p["exchange2"], p["leg2_token"]))

        if self._ws_worker:
            self._ws_worker.stop()
            self._ws_worker.wait(3000)

        self._ws_worker = WebSocketWorker(self._client, self)
        self._ws_worker.set_subscriptions(list(set(subs)))
        self._ws_worker.tick_received.connect(self._dashboard.on_tick)
        self._ws_worker.connected.connect(lambda: self._status_bar.showMessage("WebSocket connected. Live feed active."))
        self._ws_worker.disconnected.connect(lambda: self._status_bar.showMessage("WebSocket disconnected. Reconnecting…"))
        self._ws_worker.reconnect_needed.connect(self._start_websocket)
        self._ws_worker.error_occurred.connect(lambda e: logger.error(f"WS error: {e}"))
        self._ws_worker.start()

    def _add_subscription(self, exchange1, token1, exchange2, token2):
        """Subscribe newly added pair tokens to live WebSocket feed."""
        if self._ws_worker and self._client:
            subs = []
            if token1:
                subs.append((exchange1, token1))
            if token2:
                subs.append((exchange2, token2))
            if subs:
                self._client.subscribe_tokens(subs)

    # ──────────────────────────────────────────────────────────────
    #   9:15 AM – Open Price Execution
    # ──────────────────────────────────────────────────────────────

    @pyqtSlot()
    def _on_open_price_trigger(self):
        logger.info("9:15 trigger: fetching open prices for pending pairs")
        self._status_bar.showMessage("09:15 IST — Fetching opening prices…")

        pending = self._db.get_pending_pairs()
        if not pending:
            self._status_bar.showMessage("09:15 IST — No pending pairs to activate.")
            return

        activated = 0
        for pair in pending:
            pid = pair["id"]
            if self._client:
                e1 = self._client.get_open_price(pair["exchange1"], pair["leg1_token"])
                e2 = self._client.get_open_price(pair["exchange2"], pair["leg2_token"])
            else:
                logger.warning(f"No Shoonya connection; skipping pair {pid}")
                continue

            if e1 is None or e2 is None:
                logger.warning(f"Pair {pid}: could not fetch open price (e1={e1}, e2={e2}). Skipping.")
                continue

            self._db.update_entry_prices(pid, e1, e2)
            self._dashboard.activate_pair(pid, e1, e2)
            activated += 1
            logger.info(f"Pair {pid} activated at open: {pair['leg1_sym']}={e1}, {pair['leg2_sym']}={e2}")

        self._status_bar.showMessage(
            f"09:15 IST — {activated}/{len(pending)} pairs activated at open prices."
        )

    # ──────────────────────────────────────────────────────────────
    #   15:35 PM – EOD CSV Export
    # ──────────────────────────────────────────────────────────────

    @pyqtSlot()
    def _on_eod_export(self):
        logger.info("15:35 trigger: exporting daily trade CSV")
        try:
            from auth import _load_env
            _load_env()
        except Exception:
            pass

        reports_dir = os.environ.get("REPORTS_DIR", "Reports")
        os.makedirs(reports_dir, exist_ok=True)

        date_str = _now_ist().strftime("%Y-%m-%d")
        filename = os.path.join(reports_dir, f"SpreadTrader_{date_str}.csv")

        history = self._db.get_today_history()
        active = self._db.get_active_pairs()

        fieldnames = [
            "type", "pair_id", "leg1_sym", "leg1_qty", "leg2_sym", "leg2_qty",
            "entry_price_1", "entry_price_2", "exit_price_1", "exit_price_2",
            "realized_pnl", "unrealized_pnl", "opened_at", "closed_at",
        ]

        try:
            with open(filename, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()

                for h in history:
                    row = dict(h)
                    row["type"] = "CLOSED"
                    row["unrealized_pnl"] = ""
                    writer.writerow(row)

                for p in active:
                    state = self._engine.get_state(p["id"])
                    row = {
                        "type": "OPEN",
                        "pair_id": p["id"],
                        "leg1_sym": p["leg1_sym"],
                        "leg1_qty": p["leg1_qty"],
                        "leg2_sym": p["leg2_sym"],
                        "leg2_qty": p["leg2_qty"],
                        "entry_price_1": p.get("entry_price_1", ""),
                        "entry_price_2": p.get("entry_price_2", ""),
                        "exit_price_1": "",
                        "exit_price_2": "",
                        "realized_pnl": "",
                        "unrealized_pnl": f"{state.pnl:.2f}" if (state and state.pnl is not None) else "",
                        "opened_at": p.get("activated_at", ""),
                        "closed_at": "",
                    }
                    writer.writerow(row)

            logger.info(f"EOD CSV exported to: {filename}")
            self._status_bar.showMessage(f"EOD report saved: {filename}")
            QMessageBox.information(
                self,
                "Report Exported",
                f"Daily report saved to:\n{filename}",
            )
        except Exception as e:
            logger.exception("EOD CSV export failed")
            self._status_bar.showMessage(f"Export failed: {e}")

    # ──────────────────────────────────────────────────────────────
    #   Add Pair
    # ──────────────────────────────────────────────────────────────

    def _on_add_pair(self):
        dlg = AddPairDialog(shoonya_client=self._client, parent=self)
        if dlg.exec() != AddPairDialog.DialogCode.Accepted:
            return
        data = dlg.get_pair_data()

        now = _now_ist()
        market_open = now.hour > 9 or (now.hour == 9 and now.minute >= 15)

        pair_id = self._db.add_pair(
            exchange1=data["exchange1"],
            leg1_sym=data["leg1_sym"],
            leg1_token=data["leg1_token"],
            leg1_qty=data["leg1_qty"],
            exchange2=data["exchange2"],
            leg2_sym=data["leg2_sym"],
            leg2_token=data["leg2_token"],
            leg2_qty=data["leg2_qty"],
        )

        pair_row = self._db.get_pair(pair_id)
        self._dashboard.add_new_pair(pair_row)

        # Subscribe this pair to the live feed
        self._add_subscription(
            data["exchange1"], data["leg1_token"],
            data["exchange2"], data["leg2_token"],
        )

        if market_open and self._client:
            # Fetch open prices immediately (intra-day add)
            e1 = self._client.get_ltp(data["exchange1"], data["leg1_token"])
            e2 = self._client.get_ltp(data["exchange2"], data["leg2_token"])
            if e1 and e2:
                self._db.update_entry_prices(pair_id, e1, e2)
                self._dashboard.activate_pair(pair_id, e1, e2)
                self._status_bar.showMessage(
                    f"Pair {data['leg1_sym']}/{data['leg2_sym']} activated at current LTP."
                )
            else:
                self._status_bar.showMessage(
                    f"Pair added. Could not fetch LTP — check WebSocket connection."
                )
        else:
            self._status_bar.showMessage(
                f"Pair {data['leg1_sym']}/{data['leg2_sym']} queued as Pending (before 09:15 IST)."
            )

    # ──────────────────────────────────────────────────────────────
    #   Called by DashboardTab after Square Off
    # ──────────────────────────────────────────────────────────────

    def refresh_history(self):
        self._history.refresh()

    # ──────────────────────────────────────────────────────────────
    #   Cleanup
    # ──────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        self._scheduler.stop()
        if self._ws_worker:
            self._ws_worker.stop()
            self._ws_worker.wait(3000)
        self._db.close()
        event.accept()
