# 📈 SpreadTrader — Virtual Pairs Desk

SpreadTrader is a macOS desktop application for **virtual pair trading** on Indian equity markets via the [Shoonya (Finvasia) API](https://api.shoonya.com/). It provides a live dashboard with real-time PnL tracking, automated daily lifecycle management, and end-of-day report export — all without placing any real orders.

---

## Features

- **Live Dashboard** — Real-time PnL (₹ and %) per pair, sourced from the Shoonya WebSocket feed
- **Virtual Pair Tracking** — Track a long/short pair across any NSE/BSE symbols with configurable quantities
- **Automated Lifecycle**
  - **09:15 IST** — Pairs added before market open are automatically activated at opening prices
  - **15:15 IST** — All active pairs are auto squared-off at current LTP
  - **15:35 IST** — A CSV report for the day is exported automatically
- **PnL engine** — Computes `(LTP_A − Entry_A) × Qty_A + (Entry_B − LTP_B) × Qty_B` in real-time; tracks intraday highest/lowest PnL per pair
- **Trade History Tab** — Browse and filter historical closed pairs
- **Dark Mode UI** — Built with PyQt6 with a polished dark theme; flash animations on PnL updates

---

## Screenshot

> *(Add a screenshot here)*

---

## Getting Started

### Prerequisites

- Python 3.11+
- A [Shoonya / Finvasia](https://shoonya.finvasia.com/) trading account with API access enabled
- macOS (Big Sur 11.0+ recommended for the `.app` bundle)

### 1. Clone the repository

```bash
git clone https://github.com/<your-username>/spreadtrader.git
cd spreadtrader
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure credentials

Copy `.env.example` to `.env` and fill in your Shoonya API credentials:

```bash
cp .env.example .env
```

```dotenv
SHOONYA_USER_ID=your_user_id
SHOONYA_PASSWORD=your_password
SHOONYA_API_KEY=your_api_key
SHOONYA_TOTP_SECRET=your_base32_totp_secret   # base-32 secret from your authenticator app
SHOONYA_VENDOR_CODE=your_vendor_code
SHOONYA_IMEI=your_imei

# Optional: directory where daily CSV reports are saved
REPORTS_DIR=/Users/you/SpreadTrader/Reports
```

> **Never commit your `.env` file.** It is already listed in `.gitignore`.

### 4. Run

```bash
python app.py
```

---

## Building the macOS App Bundle

SpreadTrader ships with a `spreadtrader.spec` for [PyInstaller](https://pyinstaller.org/):

```bash
pip install pyinstaller
pyinstaller spreadtrader.spec
```

The output `.app` bundle will be at `dist/SpreadTrader.app`. Copy it to `/Applications` or your Desktop:

```bash
cp -R dist/SpreadTrader.app ~/Desktop/
```

---

## Usage

1. **Launch SpreadTrader** — it attempts Shoonya login automatically on startup.
2. **Add a pair** — Click **＋ Add Pair** in the toolbar and enter the two legs (symbol, exchange, quantity).
3. **Monitor** — The Live Dashboard updates in real-time as ticks arrive over the WebSocket.
4. **Square Off** — Click **■ S/O** on any active row to manually close the pair at current LTP.
5. **Reports** — The daily CSV is auto-saved at 15:35 IST, or you can wait for the status bar message with the file path.

---

## Project Structure

```
spreadtrader/
├── app.py               # Entry point; sets up logging and launches the Qt app
├── main_window.py       # QMainWindow: toolbar, tabs, lifecycle orchestration
├── dashboard_tab.py     # Live PnL table with WebSocket-driven updates
├── history_tab.py       # Trade history browser
├── add_pair_dialog.py   # Dialog for adding new pairs (with symbol search)
├── pnl_engine.py        # In-memory PnL state machine
├── db.py                # SQLite database layer (pairs, history, PnL snapshots)
├── shoonya_client.py    # Shoonya REST API wrapper
├── auth.py              # Login helper (TOTP + env loading)
├── websocket_worker.py  # QThread wrapping the Shoonya WebSocket feed
├── scheduler.py         # Qt-based market scheduler (09:15 / 15:15 / 15:35 triggers)
├── requirements.txt
├── spreadtrader.spec    # PyInstaller build spec for macOS .app
└── .env.example         # Credentials template
```

---

## PnL Formula

SpreadTrader tracks a **virtual** long-short spread. No real orders are placed.

```
PnL = (LTP_A − Entry_A) × Qty_A + (Entry_B − LTP_B) × Qty_B
```

- **Leg A** is treated as the long leg.
- **Leg B** is treated as the short leg.
- PnL % is calculated against total deployed capital (`Entry_A × Qty_A + Entry_B × Qty_B`).

Intraday highest and lowest PnL watermarks are stored per-pair and recorded at close.

---

## Data Storage

All data is persisted in a local SQLite database (`spreadtrader.db`, excluded from Git). Logs are written to `~/Library/Application Support/SpreadTrader/spreadtrader.log` (rotating, max 5 MB × 3 files).

---

## Dependencies

| Package | Purpose |
|---|---|
| `PyQt6` | Desktop GUI framework |
| `NorenRestApiPy` | Shoonya REST & WebSocket API |
| `websocket-client` | WebSocket transport |
| `pyotp` | TOTP two-factor auth |
| `python-dotenv` | `.env` credential loading |
| `pytz` | IST timezone handling |
| `pyqtgraph` | Intraday spread/PnL charts |
| `numpy` | Numerical ops for charting |
| `Pillow` | Image processing for icons |
| `pyinstaller` | macOS `.app` bundling |

---

## License

MIT — see [LICENSE](LICENSE) for details.
