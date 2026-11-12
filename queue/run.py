"""서버 실행: python run.py  (같은 와이파이의 휴대폰에서 접속 가능하도록 0.0.0.0 으로 엶)"""

import os
import sys
from pathlib import Path

import uvicorn

if __name__ == "__main__":
    # 어느 폴더에서 실행해도 이 폴더의 .env 와 queue.db 를 사용
    here = Path(__file__).resolve().parent
    os.chdir(here)
    sys.path.insert(0, str(here))
    uvicorn.run(
        "app.main:app",
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8000")),
        # SSE 연결이 열려 있어도 Ctrl+C 시 빨리 종료되도록
        timeout_graceful_shutdown=2,
        proxy_headers=True,
    )
