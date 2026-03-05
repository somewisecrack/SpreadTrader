"""
dashboard_tab.py – Live pair dashboard with real-time PnL indicators.

Shows a QTableWidget with all active/pending pairs.
PnL cells animate green↔red on update via background flash.
Square Off and Delete actions are per-row.
"""
import logging

from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QVariantAnimation, pyqtSlot
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QMessageBox,
)

logger = logging.getLogger("SpreadTrader.DashboardTab")

STATUS_COLORS = {
    "pending":  "#f59e0b",
    "active":   "#4ade80",
    "closed":   "#94a3b8",
}

COLUMNS = [
    ("Leg 1",   100),
    ("Qty",     40),
    ("Leg 2",   100),
    ("Qty",     40),
    ("Entry 1", 80),
    ("Entry 2", 80),
    ("LTP 1",   80),
    ("LTP 2",   80),
    ("PnL (₹)", 90),
    ("PnL (%)", 80),
    ("Status",  70),
    ("Square Off", 90),
    ("Delete",  65),
]

COL = {name: i for i, (name, _) in enumerate(COLUMNS)}
# Two columns share the name "Qty" — define both explicitly
COL_QTY1 = 1   # leg 1 qty
COL_QTY2 = 3   # leg 2 qty


def _ro(text: str, align=Qt.AlignmentFlag.AlignLeft) -> QTableWidgetItem:
    item = QTableWidgetItem(str(text) if text is not None else "—")
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    item.setTextAlignment(align | Qt.AlignmentFlag.AlignVCenter)
    return item


class DashboardTab(QWidget):

    def __init__(self, db, pnl_engine, shoonya_client=None, parent=None):
        super().__init__(parent)
        self._db = db
        self._engine = pnl_engine
        self._client = shoonya_client
        self._flash_timers: dict[int, QTimer] = {}   # pair_id → flash QTimer
        self._pair_rows: dict[int, int] = {}          # pair_id → table row index
        self._build_ui()
        self._reload_all()

    def set_client(self, client):
        self._client = client

    # ──────────────────────────────────────────────────────────────
    #   UI
    # ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Header
        hdr = QHBoxLayout()
        title = QLabel("Live Dashboard")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #e2e8f0;")
        hdr.addWidget(title)
        hdr.addStretch()

        self._total_pnl_label = QLabel("Total PnL: —")
        self._total_pnl_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #94a3b8;")
        hdr.addWidget(self._total_pnl_label)
        layout.addLayout(hdr)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(len(COLUMNS))
        self._table.setHorizontalHeaderLabels([c[0] for c in COLUMNS])
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        for i, (_, w) in enumerate(COLUMNS):
            self._table.setColumnWidth(i, w)
        self._table.horizontalHeader().setSectionResizeMode(
            COL["PnL (₹)"], QHeaderView.ResizeMode.Stretch
        )

        self._table.setStyleSheet(
            """
            QTableWidget { background: #0f172a; color: #e2e8f0; gridline-color: #1e293b;
                           border: none; border-radius: 8px; font-size: 12px; }
            QTableWidget::item { padding: 6px; border-bottom: 1px solid #1e293b; }
            QTableWidget::item:selected { background: #1e3a5f; }
            QTableWidget::item:alternate { background: #111827; }
            QHeaderView::section { background: #1e293b; color: #94a3b8; padding: 6px;
                                   border: none; font-weight: bold; }
            """
        )
        layout.addWidget(self._table)

    # ──────────────────────────────────────────────────────────────
    #   Data Loading
    # ──────────────────────────────────────────────────────────────

    def _reload_all(self):
        """Full table rebuild from DB + engine state."""
        pairs = self._db.get_active_pairs()
        self._engine.load_pairs(pairs)
        self._table.setRowCount(0)
        self._pair_rows.clear()
        for p in pairs:
            self._add_row(p)
        self._update_total_pnl()

    def _add_row(self, pair: dict):
        r = self._table.rowCount()
        self._table.insertRow(r)
        pid = pair["id"]
        self._pair_rows[pid] = r
        self._fill_row(r, pair)

    def _fill_row(self, r: int, pair: dict):
        pid = pair["id"]
        status = pair.get("status", "pending")


        self._table.setItem(r, COL["Leg 1"], _ro(pair["leg1_sym"]))
        self._table.setItem(r, COL_QTY1,     _ro(pair["leg1_qty"], Qt.AlignmentFlag.AlignHCenter))
        self._table.setItem(r, COL["Leg 2"], _ro(pair["leg2_sym"]))
        self._table.setItem(r, COL_QTY2,     _ro(pair["leg2_qty"], Qt.AlignmentFlag.AlignHCenter))

        e1 = pair.get("entry_price_1")
        e2 = pair.get("entry_price_2")
        self._table.setItem(r, COL["Entry 1"], _ro(f"{e1:.2f}" if e1 else "—", Qt.AlignmentFlag.AlignRight))
        self._table.setItem(r, COL["Entry 2"], _ro(f"{e2:.2f}" if e2 else "—", Qt.AlignmentFlag.AlignRight))

        ltp1 = pair.get("ltp_1")
        ltp2 = pair.get("ltp_2")
        self._table.setItem(r, COL["LTP 1"], _ro(f"{ltp1:.2f}" if ltp1 else "—", Qt.AlignmentFlag.AlignRight))
        self._table.setItem(r, COL["LTP 2"], _ro(f"{ltp2:.2f}" if ltp2 else "—", Qt.AlignmentFlag.AlignRight))

        pnl_item = _ro("—", Qt.AlignmentFlag.AlignRight)
        pnl_item.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        self._table.setItem(r, COL["PnL (₹)"], pnl_item)

        pct_item = _ro("—", Qt.AlignmentFlag.AlignRight)
        pct_item.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        self._table.setItem(r, COL["PnL (%)"], pct_item)

        status_item = _ro(status.capitalize(), Qt.AlignmentFlag.AlignHCenter)
        status_item.setForeground(QColor(STATUS_COLORS.get(status, "#94a3b8")))
        self._table.setItem(r, COL["Status"], status_item)

        # Square Off button
        sq_btn = QPushButton("■ S/O")
        sq_btn.setFixedWidth(80)
        sq_btn.setEnabled(status == "active")
        sq_btn.setStyleSheet(
            "QPushButton { background: #1e40af; color: #bfdbfe; border-radius: 4px; font-size: 11px; }"
            " QPushButton:hover { background: #1d4ed8; }"
            " QPushButton:disabled { background: #1e293b; color: #475569; }"
        )
        sq_btn.clicked.connect(lambda _, p=pid: self._square_off(p))
        self._table.setCellWidget(r, COL["Square Off"], sq_btn)

        # Delete button
        del_btn = QPushButton("🗑")
        del_btn.setFixedWidth(55)
        del_btn.setStyleSheet(
            "QPushButton { background: #7f1d1d; color: #fca5a5; border-radius: 4px; }"
            " QPushButton:hover { background: #991b1b; }"
        )
        del_btn.clicked.connect(lambda _, p=pid: self._delete_pair(p))
        self._table.setCellWidget(r, COL["Delete"], del_btn)

    # ──────────────────────────────────────────────────────────────
    #   Real-time PnL Update (called by MainWindow slot)
    # ──────────────────────────────────────────────────────────────

    @pyqtSlot(str, float)
    def on_tick(self, token: str, ltp: float):
        """Receive a WebSocket tick and update affected rows."""
        changed_ids = self._engine.update_tick(token, ltp)
        for pid in changed_ids:
            self._refresh_pnl_cell(pid)
            self._update_ltp_cells(pid)
        if changed_ids:
            self._update_total_pnl()

    def _refresh_pnl_cell(self, pair_id: int):
        r = self._pair_rows.get(pair_id)
        if r is None:
            return
        state = self._engine.get_state(pair_id)
        if state is None:
            return

        pnl = state.pnl
        pct = state.pnl_pct
        
        item_pnl = self._table.item(r, COL["PnL (₹)"])
        item_pct = self._table.item(r, COL["PnL (%)"])
        
        if item_pnl is None or item_pct is None:
            return

        if pnl is None or pct is None:
            item_pnl.setText("—")
            item_pct.setText("—")
            return

        sign = "+" if pnl >= 0 else ""
        color = QColor("#4ade80") if pnl >= 0 else QColor("#f87171")
        
        item_pnl.setText(f"{sign}{pnl:,.2f}")
        item_pnl.setForeground(color)
        
        item_pct.setText(f"{sign}{pct:.2f}%")
        item_pct.setForeground(color)

        # Flash background
        self._flash_cell(r, COL["PnL (₹)"], pnl >= 0)
        self._flash_cell(r, COL["PnL (%)"], pnl >= 0)

    def _update_ltp_cells(self, pair_id: int):
        r = self._pair_rows.get(pair_id)
        if r is None:
            return
        state = self._engine.get_state(pair_id)
        if state is None:
            return
        if state.ltp_1 is not None:
            item = self._table.item(r, COL["LTP 1"])
            if item:
                item.setText(f"{state.ltp_1:.2f}")
        if state.ltp_2 is not None:
            item = self._table.item(r, COL["LTP 2"])
            if item:
                item.setText(f"{state.ltp_2:.2f}")

    def _flash_cell(self, row: int, col: int, positive: bool):
        """Brief background flash: green flash for gain, red for loss."""
        flash_color = QColor("#166534") if positive else QColor("#7f1d1d")
        normal_color = QColor("#0f172a") if row % 2 == 0 else QColor("#111827")

        item = self._table.item(row, col)
        if not item:
            return
        item.setBackground(flash_color)

        t = QTimer(self)
        t.setSingleShot(True)
        t.setInterval(400)
        t.timeout.connect(lambda: self._clear_flash(item, normal_color))
        t.start()

    def _clear_flash(self, item, color):
        if item:
            item.setBackground(color)

    def _update_total_pnl(self):
        active_states = [s for s in self._engine.get_all_states() if s.status == "active"]
        total_pnl = sum((s.pnl or 0.0) for s in active_states)
        total_cap = sum((s.deployed_capital or 0.0) for s in active_states)
        
        sign = "+" if total_pnl >= 0 else ""
        color = "#4ade80" if total_pnl >= 0 else "#f87171"
        
        if total_cap > 0:
            total_pct = (total_pnl / total_cap) * 100.0
            pct_str = f" ({sign}{total_pct:.2f}%)"
        else:
            pct_str = ""
            
        self._total_pnl_label.setText(
            f"Total PnL: <span style='color:{color}'>{sign}{total_pnl:,.2f} ₹{pct_str}</span>"
        )

    # ──────────────────────────────────────────────────────────────
    #   Actions
    # ──────────────────────────────────────────────────────────────

    def _square_off(self, pair_id: int):
        state = self._engine.get_state(pair_id)
        if not state or state.status != "active":
            QMessageBox.warning(self, "Square Off", "Pair is not currently active.")
            return

        ltp1 = state.ltp_1
        ltp2 = state.ltp_2

        if ltp1 is None or ltp2 is None:
            # Fallback: fetch via REST
            pair_row = self._db.get_pair(pair_id)
            if self._client and pair_row:
                ltp1 = ltp1 or self._client.get_ltp(pair_row["exchange1"], pair_row["leg1_token"])
                ltp2 = ltp2 or self._client.get_ltp(pair_row["exchange2"], pair_row["leg2_token"])

        if ltp1 is None or ltp2 is None:
            QMessageBox.warning(
                self,
                "Square Off",
                "Cannot fetch current price for one or both legs.\n"
                "Ensure Shoonya is connected and the WebSocket is live.",
            )
            return

        pnl = state.pnl or (
            (ltp1 - state.entry_price_1) * state.leg1_qty
            + (state.entry_price_2 - ltp2) * state.leg2_qty
        )

        reply = QMessageBox.question(
            self,
            "Confirm Square Off",
            f"Close pair {state.leg1_sym}/{state.leg2_sym}?\n\n"
            f"Exit prices: {ltp1:.2f} / {ltp2:.2f}\n"
            f"Realized PnL: {'+'if pnl>=0 else ''}{pnl:.2f} ₹",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._db.close_pair(
            pair_id, ltp1, ltp2, pnl,
            highest_pnl=state.highest_pnl or 0.0,
            lowest_pnl=state.lowest_pnl or 0.0
        )
        self._engine.close_pair(pair_id)
        self._reload_all()

        # Notify parent to refresh history tab
        parent = self.parent()
        while parent:
            if hasattr(parent, "refresh_history"):
                parent.refresh_history()
                break
            parent = parent.parent()

    def _delete_pair(self, pair_id: int):
        state = self._engine.get_state(pair_id)
        sym = f"{state.leg1_sym}/{state.leg2_sym}" if state else "this pair"
        reply = QMessageBox.question(
            self,
            "Delete Pair",
            f"Permanently delete pair {sym}?\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._db.delete_pair(pair_id)
            self._engine.remove_pair(pair_id)
            self._reload_all()

    # ──────────────────────────────────────────────────────────────
    #   Public API called by MainWindow
    # ──────────────────────────────────────────────────────────────

    def add_new_pair(self, pair_row: dict):
        """Called after a new pair is inserted into the DB."""
        self._engine.load_pairs([pair_row])
        self._add_row(pair_row)
        self._update_total_pnl()

    def activate_pair(self, pair_id: int, entry_price_1: float, entry_price_2: float):
        """Called by MainWindow when 9:15 trigger fires."""
        self._engine.activate_pair(pair_id, entry_price_1, entry_price_2)
        r = self._pair_rows.get(pair_id)
        if r is not None:
            self._table.item(r, COL["Entry 1"]).setText(f"{entry_price_1:.2f}")
            self._table.item(r, COL["Entry 2"]).setText(f"{entry_price_2:.2f}")
            status_item = self._table.item(r, COL["Status"])
            if status_item:
                status_item.setText("Active")
                status_item.setForeground(QColor(STATUS_COLORS["active"]))
            sq_btn = self._table.cellWidget(r, COL["Square Off"])
            if sq_btn:
                sq_btn.setEnabled(True)
        self._update_total_pnl()

    def reload(self):
        self._reload_all()
