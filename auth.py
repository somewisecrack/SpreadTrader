"""
auth.py – Shoonya API login with automatic TOTP generation.
Loads credentials from .env (same folder as executable in frozen mode).
"""
import os
import sys
import logging
import pyotp
from dotenv import load_dotenv

logger = logging.getLogger("SpreadTrader.Auth")


def _load_env():
    """Load .env from executable directory (frozen) or project root (dev)."""
    if getattr(sys, "frozen", False):
        # Running as PyInstaller bundle
        env_dir = os.path.dirname(sys.executable)
    else:
        env_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(env_dir, ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path)
        logger.info(f"Loaded .env from: {env_path}")
    else:
        logger.warning(f".env not found at {env_path}. Falling back to environment variables.")


def get_credentials() -> dict:
    """Return a dict of all required Shoonya credentials."""
    _load_env()
    required = [
        "SHOONYA_USER_ID",
        "SHOONYA_PASSWORD",
        "SHOONYA_API_KEY",
        "SHOONYA_TOTP_SECRET",
        "SHOONYA_VENDOR_CODE",
        "SHOONYA_IMEI",
    ]
    creds = {}
    missing = []
    for key in required:
        val = os.environ.get(key, "").strip()
        if not val:
            missing.append(key)
        creds[key] = val
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            "Please fill in your .env file."
        )
    return creds


def generate_totp(totp_secret: str) -> str:
    """Generate a 6-digit TOTP code from the base-32 secret."""
    totp = pyotp.TOTP(totp_secret)
    code = totp.now()
    logger.debug(f"Generated TOTP: {code}")
    return code


def login_shoonya():
    """
    Log in to Shoonya API and return the authenticated NorenApi instance.
    Returns (api, None) on success, (None, error_message) on failure.
    """
    try:
        from NorenRestApiPy.NorenApi import NorenApi  # type: ignore

        creds = get_credentials()
        totp_code = generate_totp(creds["SHOONYA_TOTP_SECRET"])

        class _ShoonyaApi(NorenApi):
            def __init__(self):
                super().__init__(
                    host="https://api.shoonya.com/NorenWClientTP/",
                    websocket="wss://api.shoonya.com/NorenWSTP/",
                )

        api = _ShoonyaApi()
        ret = api.login(
            userid=creds["SHOONYA_USER_ID"],
            password=creds["SHOONYA_PASSWORD"],
            twoFA=totp_code,
            vendor_code=creds["SHOONYA_VENDOR_CODE"],
            api_secret=creds["SHOONYA_API_KEY"],
            imei=creds["SHOONYA_IMEI"],
        )

        if ret is None or (isinstance(ret, dict) and ret.get("stat") == "Not_Ok"):
            msg = ret.get("emsg", "Unknown login error") if isinstance(ret, dict) else "Login returned None"
            logger.error(f"Shoonya login failed: {msg}")
            return None, msg

        logger.info(f"Shoonya login SUCCESS for user: {creds['SHOONYA_USER_ID']}")
        return api, None

    except ImportError:
        msg = "NorenRestApiPy not installed. Run: pip install NorenRestApiPy"
        logger.error(msg)
        return None, msg
    except RuntimeError as e:
        return None, str(e)
    except Exception as e:
        logger.exception("Unexpected error during Shoonya login")
        return None, str(e)
