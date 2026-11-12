import os
import secrets

from dotenv import load_dotenv

load_dotenv()

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
STORE_NAME = os.environ.get("STORE_NAME", "순번 대기")
RETENTION_DAYS = int(os.environ.get("RETENTION_DAYS", "30"))
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./queue.db")
