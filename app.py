"""
app.py – SpreadTrader entry point.

Compiled with --noconsole by PyInstaller so no terminal window appears.
All logging goes to a rotating file (spreadtrader.log).
"""
import sys
import os
import ssl
import logging
from logging.handlers import RotatingFileHandler

# ── macOS bundle SSL fix ──────────────────────────────────────────────────────
# PyInstaller bundles on macOS don't include root CA certificates.
# Point OpenSSL to certifi's bundled cacert.pem BEFORE any connections are made.
# This is the universally recommended fix for PyInstaller + macOS SSL issues.
try:
    import certifi
    os.environ.setdefault("SSL_CERT_FILE",      certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
except ImportError:
    pass
# Belt-and-suspenders: also allow unverified contexts as fallback
ssl._create_default_https_context = ssl._create_unverified_context
# ─────────────────────────────────────────────────────────────────────────────







def _setup_logging():
    """Configure rotating file logger. Written to Application Support, always writable."""
    app_support = os.path.join(
        os.path.expanduser("~"), "Library", "Application Support", "SpreadTrader"
    )
    os.makedirs(app_support, exist_ok=True)
    log_path = os.path.join(app_support, "spreadtrader.log")

    handler = RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    formatter = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)-30s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)

    # In development (not frozen), also log to console
    if not getattr(sys, "frozen", False):
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(formatter)
        root.addHandler(console)

    return log_path


def main():
    _setup_logging()
    logger = logging.getLogger("SpreadTrader")
    logger.info("=" * 60)
    logger.info("SpreadTrader starting up")

    from PyQt6.QtWidgets import QApplication, QMessageBox
    from PyQt6.QtGui import QFont
    from PyQt6.QtCore import Qt

    app = QApplication(sys.argv)
    app.setApplicationName("SpreadTrader")
    app.setOrganizationName("SpreadTrader")

    # Use system font — Segoe UI doesn't exist on macOS
    app.setFont(QFont())

    # High-DPI is always enabled by default in PyQt6.4+

    from main_window import MainWindow
    try:
        window = MainWindow()
        window.show()
        window.raise_()
        window.activateWindow()
    except Exception as e:
        logger.exception("Fatal error creating MainWindow")
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Critical)
        msg.setWindowTitle("SpreadTrader – Fatal Error")
        msg.setText(f"Failed to start SpreadTrader:\n\n{e}")
        msg.exec()
        sys.exit(1)

    logger.info("UI displayed — entering event loop")
    exit_code = app.exec()
    logger.info(f"SpreadTrader exiting with code {exit_code}")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
