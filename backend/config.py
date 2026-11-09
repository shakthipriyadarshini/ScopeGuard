"""App settings. Everything secret comes from environment variables (.env)."""
import os

from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))  # reads backend/.env if it exists


class Config:
    # No default on purpose: the app refuses to start without a real key
    SECRET_KEY = os.environ.get("SECRET_KEY")
    # SQLite file inside backend/ unless DATABASE_URL says otherwise
    DATABASE_URL = os.environ.get(
        "DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "scopeguard.db")
    )
