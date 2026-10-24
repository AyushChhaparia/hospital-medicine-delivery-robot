import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory
BASE_DIR = Path(__file__).resolve().parent

# Load .env file
load_dotenv(BASE_DIR / ".env")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "hospital-super-secret-key-2026-prod-fallback")
    
    # SQLite database file inside instance folder
    INSTANCE_DIR = BASE_DIR / "instance"
    INSTANCE_DIR.mkdir(exist_ok=True)
    
    db_path = INSTANCE_DIR / "hospital.db"
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", f"sqlite:///{db_path}")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Robot API Token for ESP32 / hardware clients
    ROBOT_API_TOKEN = os.environ.get("ROBOT_API_TOKEN", "esp32-hospital-robot-secure-token-2026")
    
    # Security & session cookies
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None  # Prevent CSRF token expiry issues in long dashboards


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "test-secret-key"
