"""
config.py - Application and database settings.

Values are read from a local .env file (never commit it to Git).
If a value is missing, the XAMPP defaults below are used.
"""
import os

from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


class Config:
    # ---- Flask ---------------------------------------------------------
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
    DEBUG = os.getenv("FLASK_DEBUG", "1") == "1"

    # ---- MySQL / MariaDB (XAMPP defaults) -------------------------------
    # 127.0.0.1 is used instead of "localhost" to avoid IPv6 lookup problems.
    DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
    DB_PORT = int(os.getenv("DB_PORT", "3306"))
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")  # XAMPP root has no password by default
    DB_NAME = os.getenv("DB_NAME", "university_medical_center")
    DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))

    # ---- AI Chatbot (Phase 7) - Google Gemini ---------------------------
    CHATBOT_ENABLED = os.getenv("CHATBOT_ENABLED", "1") == "1"
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    # Model names change often - see https://ai.google.dev/gemini-api/docs/deprecations
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    GEMINI_THINKING_LEVEL = os.getenv("GEMINI_THINKING_LEVEL", "")  # "" = model default
    GEMINI_TIMEOUT_SECONDS = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "30"))

    CHATBOT_MAX_MESSAGE_LENGTH = int(os.getenv("CHATBOT_MAX_MESSAGE_LENGTH", "500"))
    CHATBOT_HISTORY_TURNS = int(os.getenv("CHATBOT_HISTORY_TURNS", "6"))
    CHATBOT_MAX_OUTPUT_TOKENS = int(os.getenv("CHATBOT_MAX_OUTPUT_TOKENS", "1024"))
    # Rate limits protect the free quota (tune using AI Studio > Rate limits)
    CHATBOT_RATE_PER_MINUTE = int(os.getenv("CHATBOT_RATE_PER_MINUTE", "6"))     # per user
    CHATBOT_RATE_PER_DAY = int(os.getenv("CHATBOT_RATE_PER_DAY", "60"))          # per user
    CHATBOT_GLOBAL_PER_MINUTE = int(os.getenv("CHATBOT_GLOBAL_PER_MINUTE", "10"))  # everyone
    CENTER_EMERGENCY_PHONE = os.getenv("CENTER_EMERGENCY_PHONE", "")  # shown in emergency replies
