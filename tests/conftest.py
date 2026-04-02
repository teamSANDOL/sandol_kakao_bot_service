from pathlib import Path
import os
import sys


os.environ.setdefault("DEBUG", "true")
os.environ.setdefault(
    "TOKEN_ENCRYPTION_KEY",
    "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
)
os.environ.setdefault("RELAY_CLIENT_SECRETS", "test-relay-secret")
os.environ.setdefault("KC_SERVER_URL", "https://sandol.sio2.kr/auth/")
os.environ.setdefault("KC_CLIENT_ID", "sandol-kakao-bot")
os.environ.setdefault("KC_REALM", "Sandori")

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
