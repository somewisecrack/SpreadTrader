"""
history_tab.py – Searchable trade history tab (PyQt6).
Displays closed trades from the `trade_history` DB table.
Supports live search by symbol and per-row deletion.
"""
import logging

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QMessageBox,
)

logger = logging.getLogger("SpreadTrader.HistoryTab")

HISTORY_COLUMNS = [
    ("ID", 40),
    ("Leg 1", 100),
    ("Qty", 50),
    ("Leg 2", 100),
    ("Qty", 50),
    ("Entry 1", 80),
    ("Entry 2", 80),
    ("Exit 1", 80),
    ("Exit 2", 80),
    ("High (₹)", 80),
    ("Low (₹)", 80),
    ("PnL (₹)", 90),
    ("Opened At", 140),
    ("Closed At", 140),
    ("Notes", 120),
    ("", 55),  # Plot
    ("", 55),  # Delete
]


def _money_item(value, positive_is_good=True) -> QTableWidgetItem:
    item = QTableWidgetItem(f"{value:,.2f}" if value is not None else "—")
    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    if value is not None:
        color = QColor("#4ade80") if value >= 0 else QColor("#f87171")
        if not positive_is_good:
            color = QColor("#f87171") if value >= 0 else QColor("#4ade80")
        item.setForeground(color)
    return item


def _ro(text: str) -> QTableWidgetItem:
    """Read-only table item."""
    item = QTableWidgetItem(str(text) if text is not None else "—")
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


class HistoryTab(QWidget):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self._db = db
        self._rows: list[dict] = []
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # ── Header ──
        header = QHBoxLayout()
        title = QLabel("Trade History")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #e2e8f0;")
        header.addWidget(title)
        header.addStretch()

        search_label = QLabel("🔍 Search:")
        search_label.setStyleSheet("color: #94a3b8;")
        header.addWidget(search_label)

        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Symbol name…")
        self._search_box.setFixedWidth(180)
        self._search_box.setStyleSheet(
            "QLineEdit { background: #1e293b; color: #e2e8f0; border: 1px solid #334155;"
            " border-radius: 6px; padding: 4px 8px; }"
        )
        self._search_box.textChanged.connect(self._on_search_changed)
        header.addWidget(self._search_box)

        refresh_btn = QPushButton("⟳ Refresh")
        refresh_btn.clicked.connect(self._refresh)
        refresh_btn.setStyleSheet(
            "QPushButton { background: #334155; color: #e2e8f0; border-radius: 6px;"
            " padding: 4px 12px; } QPushButton:hover { background: #475569; }"
        )
        header.addWidget(refresh_btn)
        layout.addLayout(header)

        # ── Stats row ──
        self._stats_label = QLabel()
        self._stats_label.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addWidget(self._stats_label)

        # ── Table ──
        self._table = QTableWidget()
        self._table.setColumnCount(len(HISTORY_COLUMNS))
        self._table.setHorizontalHeaderLabels([c[0] for c in HISTORY_COLUMNS])
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.setShowGrid(False)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSortingEnabled(True)

        for i, (_, w) in enumerate(HISTORY_COLUMNS):
            if w:
                self._table.setColumnWidth(i, w)
        self._table.horizontalHeader().setSectionResizeMode(
            14, QHeaderView.ResizeMode.Stretch
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

        # Search debounce timer
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._refresh)

    # ──────────────────────────────────────────────────────────────

    def _on_search_changed(self, _):
        self._search_timer.start()

    def _refresh(self):
        search = self._search_box.text().strip()
        self._rows = self._db.get_history(search)
        self._populate_table()

    def _populate_table(self):
        self._table.setRowCount(0)
        total_pnl = 0.0
        for row in self._rows:
            r = self._table.rowCount()
            self._table.insertRow(r)
            pnl = row.get("realized_pnl") or 0.0
            total_pnl += pnl

            self._table.setItem(r, 0,  _ro(r + 1))
            self._table.setItem(r, 1,  _ro(row["leg1_sym"]))
            self._table.setItem(r, 2,  _ro(row["leg1_qty"]))
            self._table.setItem(r, 3,  _ro(row["leg2_sym"]))
            self._table.setItem(r, 4,  _ro(row["leg2_qty"]))
            self._table.setItem(r, 5,  _ro(f"{row['entry_price_1']:.2f}" if row['entry_price_1'] else "—"))
            self._table.setItem(r, 6,  _ro(f"{row['entry_price_2']:.2f}" if row['entry_price_2'] else "—"))
            self._table.setItem(r, 7,  _ro(f"{row['exit_price_1']:.2f}" if row['exit_price_1'] else "—"))
            self._table.setItem(r, 8,  _ro(f"{row['exit_price_2']:.2f}" if row['exit_price_2'] else "—"))
            self._table.setItem(r, 9,  _money_item(row.get("highest_pnl")))
            self._table.setItem(r, 10, _money_item(row.get("lowest_pnl")))
            self._table.setItem(r, 11, _money_item(pnl))
            self._table.setItem(r, 12, _ro(row.get("opened_at", "—")))
            self._table.setItem(r, 13, _ro(row.get("closed_at", "—")))
            self._table.setItem(r, 14, _ro(row.get("notes", "")))

            plot_btn = QPushButton("📈 Plot")
            plot_btn.setFixedWidth(50)
            plot_btn.setStyleSheet(
                "QPushButton { background: #0ea5e9; color: white; border-radius: 4px; font-size: 11px; }"
                " QPushButton:hover { background: #38bdf8; }"
            )
            plot_btn.clicked.connect(lambda _, hid=row["pair_id"], syms=f"{row['leg1_sym']}/{row['leg2_sym']}": self._show_plot(hid, syms))
            self._table.setCellWidget(r, 15, plot_btn)

            del_btn = QPushButton("🗑 Del")
            del_btn.setFixedWidth(50)
            del_btn.setStyleSheet(
                "QPushButton { background: #7f1d1d; color: #fca5a5; border-radius: 4px; font-size: 11px; }"
                " QPushButton:hover { background: #991b1b; }"
            )
            history_id = row["id"]
            del_btn.clicked.connect(lambda _, hid=history_id: self._delete_record(hid))
            self._table.setCellWidget(r, 16, del_btn)

        sign = "+" if total_pnl >= 0 else ""
        color = "#4ade80" if total_pnl >= 0 else "#f87171"
        n = len(self._rows)
        self._stats_label.setText(
            f"<span style='color:#94a3b8'>{n} record{'s' if n != 1 else ''} | "
            f"Total PnL: <span style='color:{color};font-weight:bold'>{sign}{total_pnl:,.2f} ₹</span></span>"
        )

    def _delete_record(self, history_id: int):
        reply = QMessageBox.question(
            self,
            "Delete Record",
            "Permanently delete this history record?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._db.delete_history_record(history_id)
            self._refresh()

    def _show_plot(self, pair_id: int, symbols: str):
        series = self._db.get_pair_series(pair_id)
        if not series:
            QMessageBox.information(self, "No Data", "No intraday plot data found for this pair.")
            return

        try:
            import pyqtgraph as pg
        except ImportError:
            QMessageBox.critical(self, "Missing Library", "pyqtgraph is not installed.\\nPlease run: pip install pyqtgraph numpy")
            return

        # Prepare data
        from datetime import datetime
        x = []
        y = []
        for row in series:
            # Parse timestamp to unix seconds
            try:
                dt = datetime.fromisoformat(row["timestamp"])
                x.append(dt.timestamp())
                y.append(row["pnl"])
            except ValueError:
                continue

        if not x:
            QMessageBox.information(self, "No Data", "Invalid plot data found for this pair.")
            return

        win = pg.GraphicsLayoutWidget(show=True, title=f"Intraday PnL: {symbols}")
        win.resize(600, 400)
        
        # Add DateAxisItem
        axis = pg.DateAxisItem(orientation='bottom')
        plot = win.addPlot(title=f"Intraday PnL: {symbols}", axisItems={'bottom': axis})
        
        plot.showGrid(x=True, y=True)
        plot.setLabel('left', 'PnL', units='₹')

        # Since it's a dark theme app
        win.setBackground('#0f172a')
        
        # Plot curve (Green if ending PnL >= 0, Red if < 0)
        color = '#4ade80' if y[-1] >= 0 else '#f87171'
        plot.plot(x, y, pen=pg.mkPen(color, width=3))
        
        # Keep a reference so it doesn't get garbage collected
        if not hasattr(self, "_plot_windows"):
            self._plot_windows = []
        self._plot_windows.append(win)

    def refresh(self):
        """Public method — called by MainWindow after a Square Off."""
        self._refresh()
