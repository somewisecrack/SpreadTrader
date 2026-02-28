"""
add_pair_dialog.py – QDialog for adding a new virtual pair.

Fields:
  Exchange 1, Leg 1 Symbol / Token, Leg 1 Qty
  Exchange 2, Leg 2 Symbol / Token, Leg 2 Qty

Includes an optional live search button for resolving symbol → token
when a ShoonyaClient is available.
"""
import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

logger = logging.getLogger("SpreadTrader.AddPairDialog")

EXCHANGES = ["NSE", "BSE", "NFO", "MCX", "CDS"]


class AddPairDialog(QDialog):
    """
    Modal dialog to input a new virtual pair.
    Returns the entered data via .get_pair_data() after exec().
    """

    def __init__(self, shoonya_client=None, parent=None):
        super().__init__(parent)
        self._client = shoonya_client
        self.setWindowTitle("Add Virtual Pair")
        self.setMinimumWidth(460)
        self._build_ui()

    # ──────────────────────────────────────────────────────────────
    #   UI Construction
    # ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(14)

        # ── Leg 1 ──
        grp1 = QGroupBox("Leg 1  (Buy)")
        grp1.setStyleSheet("QGroupBox { font-weight: bold; color: #4ade80; }")
        f1 = QFormLayout(grp1)

        self._exc1 = QComboBox()
        self._exc1.addItems(EXCHANGES)
        f1.addRow("Exchange:", self._exc1)

        sym_row1 = QHBoxLayout()
        self._sym1 = QLineEdit()
        self._sym1.setPlaceholderText("e.g. RELIANCE")
        sym_row1.addWidget(self._sym1)
        self._search_btn1 = QPushButton("Lookup →")
        self._search_btn1.setFixedWidth(80)
        self._search_btn1.clicked.connect(lambda: self._lookup(self._exc1, self._sym1, self._tok1))
        sym_row1.addWidget(self._search_btn1)
        f1.addRow("Symbol:", sym_row1)

        self._tok1 = QLineEdit()
        self._tok1.setPlaceholderText("Shoonya scrip token (numeric)")
        f1.addRow("Token:", self._tok1)

        self._qty1 = QLineEdit("1")
        self._qty1.setValidator(QIntValidator(1, 999_999))
        f1.addRow("Quantity:", self._qty1)

        root.addWidget(grp1)

        # ── Leg 2 ──
        grp2 = QGroupBox("Leg 2  (Sell)")
        grp2.setStyleSheet("QGroupBox { font-weight: bold; color: #f87171; }")
        f2 = QFormLayout(grp2)

        self._exc2 = QComboBox()
        self._exc2.addItems(EXCHANGES)
        f2.addRow("Exchange:", self._exc2)

        sym_row2 = QHBoxLayout()
        self._sym2 = QLineEdit()
        self._sym2.setPlaceholderText("e.g. HDFCBANK")
        sym_row2.addWidget(self._sym2)
        self._search_btn2 = QPushButton("Lookup →")
        self._search_btn2.setFixedWidth(80)
        self._search_btn2.clicked.connect(lambda: self._lookup(self._exc2, self._sym2, self._tok2))
        sym_row2.addWidget(self._search_btn2)
        f2.addRow("Symbol:", sym_row2)

        self._tok2 = QLineEdit()
        self._tok2.setPlaceholderText("Shoonya scrip token (numeric)")
        f2.addRow("Token:", self._tok2)

        self._qty2 = QLineEdit("1")
        self._qty2.setValidator(QIntValidator(1, 999_999))
        f2.addRow("Quantity:", self._qty2)

        root.addWidget(grp2)

        # ── Info label ──
        note = QLabel(
            "ℹ  Enter the pair and click Add. If the market is open, "
            "it becomes active immediately. Before 09:15 IST it stays 'Pending'."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #94a3b8; font-size: 11px;")
        root.addWidget(note)

        # ── Buttons ──
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Add Pair")
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    # ──────────────────────────────────────────────────────────────
    #   Symbol lookup
    # ──────────────────────────────────────────────────────────────

    def _lookup(self, exc_combo: QComboBox, sym_edit: QLineEdit, tok_edit: QLineEdit):
        if not self._client:
            QMessageBox.information(
                self,
                "Not Connected",
                "Login to Shoonya first to use symbol lookup.\n"
                "You can also enter the token manually.",
            )
            return
        search = sym_edit.text().strip().upper()
        exchange = exc_combo.currentText()
        if not search:
            return
        results = self._client.search_scrip(exchange, search)
        if not results:
            QMessageBox.warning(self, "Not Found", f"No results for '{search}' on {exchange}.")
            return
        # Pick first exact match by tsym, else first result
        match = next((r for r in results if r.get("tsym", "").upper() == search), results[0])
        tok_edit.setText(match.get("token", ""))
        sym_edit.setText(match.get("tsym", search))
        logger.info(f"Lookup: {exchange}:{search} → token={match.get('token')}")

    # ──────────────────────────────────────────────────────────────
    #   Validation
    # ──────────────────────────────────────────────────────────────

    def _validate_and_accept(self):
        errors = []
        s1 = self._sym1.text().strip().upper()
        s2 = self._sym2.text().strip().upper()
        t1 = self._tok1.text().strip()
        t2 = self._tok2.text().strip()

        if not s1:
            errors.append("Leg 1 symbol is required.")
        if not s2:
            errors.append("Leg 2 symbol is required.")
        if not t1:
            errors.append("Leg 1 token is required. Use Lookup or enter manually.")
        if not t2:
            errors.append("Leg 2 token is required. Use Lookup or enter manually.")
        if s1 and s2 and s1 == s2 and t1 == t2:
            errors.append("Leg 1 and Leg 2 cannot be identical.")

        try:
            q1 = int(self._qty1.text())
            if q1 <= 0:
                raise ValueError
        except ValueError:
            errors.append("Leg 1 quantity must be a positive integer.")

        try:
            q2 = int(self._qty2.text())
            if q2 <= 0:
                raise ValueError
        except ValueError:
            errors.append("Leg 2 quantity must be a positive integer.")

        if errors:
            QMessageBox.warning(self, "Validation Error", "\n".join(errors))
            return

        self._sym1.setText(s1)
        self._sym2.setText(s2)
        self.accept()

    # ──────────────────────────────────────────────────────────────
    #   Result accessor
    # ──────────────────────────────────────────────────────────────

    def get_pair_data(self) -> dict:
        return {
            "exchange1": self._exc1.currentText(),
            "leg1_sym":  self._sym1.text().strip().upper(),
            "leg1_token": self._tok1.text().strip(),
            "leg1_qty":  int(self._qty1.text()),
            "exchange2": self._exc2.currentText(),
            "leg2_sym":  self._sym2.text().strip().upper(),
            "leg2_token": self._tok2.text().strip(),
            "leg2_qty":  int(self._qty2.text()),
        }
