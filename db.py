"""
db.py – SQLite database layer for SpreadTrader.
Manages two tables: `pairs` (active/pending/closed) and `trade_history`.
"""
import sqlite3
import os
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger("SpreadTrader.DB")

# Store DB in ~/Library/Application Support/SpreadTrader/ — always writable
# regardless of how the app is launched (Finder, terminal, frozen bundle).
_APP_SUPPORT = os.path.join(
    os.path.expanduser("~"), "Library", "Application Support", "SpreadTrader"
)
os.makedirs(_APP_SUPPORT, exist_ok=True)
DB_FILE = os.path.join(_APP_SUPPORT, "spreadtrader.db")


class DatabaseManager:
    def __init__(self, db_path: str = DB_FILE):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = self._connect()
        return self._conn

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS pairs (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                exchange1       TEXT    NOT NULL DEFAULT 'NSE',
                leg1_sym        TEXT    NOT NULL,
                leg1_token      TEXT    NOT NULL DEFAULT '',
                leg1_qty        INTEGER NOT NULL,
                exchange2       TEXT    NOT NULL DEFAULT 'NSE',
                leg2_sym        TEXT    NOT NULL,
                leg2_token      TEXT    NOT NULL DEFAULT '',
                leg2_qty        INTEGER NOT NULL,
                entry_price_1   REAL,
                entry_price_2   REAL,
                ltp_1           REAL,
                ltp_2           REAL,
                status          TEXT    NOT NULL DEFAULT 'pending',
                created_at      TEXT    NOT NULL,
                activated_at    TEXT,
                notes           TEXT    DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS trade_history (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                pair_id         INTEGER NOT NULL,
                leg1_sym        TEXT    NOT NULL,
                leg1_qty        INTEGER NOT NULL,
                leg2_sym        TEXT    NOT NULL,
                leg2_qty        INTEGER NOT NULL,
                entry_price_1   REAL,
                entry_price_2   REAL,
                exit_price_1    REAL,
                exit_price_2    REAL,
                realized_pnl    REAL,
                highest_pnl     REAL,
                lowest_pnl      REAL,
                opened_at       TEXT,
                closed_at       TEXT    NOT NULL,
                notes           TEXT    DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS pair_series (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                pair_id         INTEGER NOT NULL,
                timestamp       TEXT    NOT NULL,
                pnl             REAL    NOT NULL
            );
            """
        )
        # Attempt to add columns for existing databases safely
        try:
            conn.execute("ALTER TABLE trade_history ADD COLUMN highest_pnl REAL;")
            conn.execute("ALTER TABLE trade_history ADD COLUMN lowest_pnl REAL;")
        except sqlite3.OperationalError:
            pass # Columns already exist

        conn.commit()
        logger.info(f"Database initialised at: {os.path.abspath(self.db_path)}")

    # ──────────────────────────────────────────────────────────────
    #   PAIRS
    # ──────────────────────────────────────────────────────────────

    def add_pair(
        self,
        exchange1: str,
        leg1_sym: str,
        leg1_token: str,
        leg1_qty: int,
        exchange2: str,
        leg2_sym: str,
        leg2_token: str,
        leg2_qty: int,
        notes: str = "",
    ) -> int:
        conn = self._get_conn()
        cur = conn.execute(
            """INSERT INTO pairs
               (exchange1, leg1_sym, leg1_token, leg1_qty,
                exchange2, leg2_sym, leg2_token, leg2_qty,
                status, created_at, notes)
               VALUES (?,?,?,?,?,?,?,?,'pending',?,?)""",
            (
                exchange1, leg1_sym, leg1_token, leg1_qty,
                exchange2, leg2_sym, leg2_token, leg2_qty,
                datetime.now().isoformat(timespec="seconds"),
                notes,
            ),
        )
        conn.commit()
        pair_id = cur.lastrowid
        logger.info(f"Added pair id={pair_id}: {leg1_sym}/{leg2_sym}")
        return pair_id

    def get_pending_pairs(self) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM pairs WHERE status='pending' ORDER BY created_at"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_active_pairs(self) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM pairs WHERE status IN ('pending','active') ORDER BY created_at"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_pair(self, pair_id: int) -> Optional[dict]:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM pairs WHERE id=?", (pair_id,)).fetchone()
        return dict(row) if row else None

    def update_entry_prices(
        self,
        pair_id: int,
        entry_price_1: float,
        entry_price_2: float,
    ):
        conn = self._get_conn()
        conn.execute(
            """UPDATE pairs
               SET entry_price_1=?, entry_price_2=?, status='active', activated_at=?
               WHERE id=?""",
            (entry_price_1, entry_price_2, datetime.now().isoformat(timespec="seconds"), pair_id),
        )
        conn.commit()
        logger.info(f"Pair id={pair_id} activated: entry1={entry_price_1}, entry2={entry_price_2}")

    def update_ltp(self, pair_id: int, ltp_1: Optional[float], ltp_2: Optional[float]):
        conn = self._get_conn()
        if ltp_1 is not None and ltp_2 is not None:
            conn.execute(
                "UPDATE pairs SET ltp_1=?, ltp_2=? WHERE id=?",
                (ltp_1, ltp_2, pair_id),
            )
        elif ltp_1 is not None:
            conn.execute("UPDATE pairs SET ltp_1=? WHERE id=?", (ltp_1, pair_id))
        elif ltp_2 is not None:
            conn.execute("UPDATE pairs SET ltp_2=? WHERE id=?", (ltp_2, pair_id))
        conn.commit()

    def close_pair(
        self,
        pair_id: int,
        exit_price_1: float,
        exit_price_2: float,
        realized_pnl: float,
        highest_pnl: float = 0.0,
        lowest_pnl: float = 0.0,
        notes: str = "",
    ) -> int:
        pair = self.get_pair(pair_id)
        if not pair:
            raise ValueError(f"Pair id={pair_id} not found")

        conn = self._get_conn()
        conn.execute("UPDATE pairs SET status='closed' WHERE id=?", (pair_id,))

        cur = conn.execute(
            """INSERT INTO trade_history
               (pair_id, leg1_sym, leg1_qty, leg2_sym, leg2_qty,
                entry_price_1, entry_price_2, exit_price_1, exit_price_2,
                realized_pnl, highest_pnl, lowest_pnl, opened_at, closed_at, notes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                pair_id,
                pair["leg1_sym"], pair["leg1_qty"],
                pair["leg2_sym"], pair["leg2_qty"],
                pair["entry_price_1"], pair["entry_price_2"],
                exit_price_1, exit_price_2,
                realized_pnl, highest_pnl, lowest_pnl,
                pair["activated_at"],
                datetime.now().isoformat(timespec="seconds"),
                notes,
            ),
        )
        conn.commit()
        hist_id = cur.lastrowid
        logger.info(f"Pair id={pair_id} closed → history id={hist_id}, PnL={realized_pnl:.2f}, High={highest_pnl:.2f}, Low={lowest_pnl:.2f}")
        return hist_id

    def delete_pair(self, pair_id: int):
        conn = self._get_conn()
        conn.execute("DELETE FROM pairs WHERE id=?", (pair_id,))
        conn.execute("DELETE FROM pair_series WHERE pair_id=?", (pair_id,))
        conn.commit()
        logger.info(f"Pair id={pair_id} permanently deleted")

    def insert_pnl_snapshot(self, pair_id: int, pnl: float):
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO pair_series (pair_id, timestamp, pnl) VALUES (?,?,?)",
            (pair_id, datetime.now().isoformat(timespec="seconds"), pnl)
        )
        conn.commit()

    def get_pair_series(self, pair_id: int) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM pair_series WHERE pair_id=? ORDER BY timestamp",
            (pair_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ──────────────────────────────────────────────────────────────
    #   HISTORY
    # ──────────────────────────────────────────────────────────────

    def get_history(self, search: str = "") -> list[dict]:
        conn = self._get_conn()
        if search:
            pattern = f"%{search}%"
            rows = conn.execute(
                """SELECT * FROM trade_history
                   WHERE leg1_sym LIKE ? OR leg2_sym LIKE ?
                   ORDER BY closed_at DESC""",
                (pattern, pattern),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM trade_history ORDER BY closed_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_history_record(self, history_id: int):
        conn = self._get_conn()
        hr = conn.execute("SELECT pair_id FROM trade_history WHERE id=?", (history_id,)).fetchone()
        if hr:
            conn.execute("DELETE FROM pair_series WHERE pair_id=?", (hr["pair_id"],))
        conn.execute("DELETE FROM trade_history WHERE id=?", (history_id,))
        conn.commit()
        logger.info(f"History record id={history_id} deleted")

    def get_today_history(self) -> list[dict]:
        """Return all trades closed today (for CSV export)."""
        today = datetime.now().date().isoformat()
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM trade_history WHERE closed_at LIKE ? ORDER BY closed_at",
            (f"{today}%",),
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
