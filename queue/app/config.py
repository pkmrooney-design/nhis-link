import os
import secrets

from dotenv import load_dotenv

load_dotenv()

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
STORE_NAME = os.environ.get("STORE_NAME", "순번 대기")
RETENTION_DAYS = int(os.environ.get("RETENTION_DAYS", "30"))
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./queue.db")
# 현황판 QR코드에 넣을 손님 접속 주소. 비우면 자동(서버 PC의 IP)으로 정함
PUBLIC_URL = os.environ.get("PUBLIC_URL", "")
