"""서버 실행: python run.py  (같은 와이파이의 휴대폰에서 접속 가능하도록 0.0.0.0 으로 엶)"""

import getpass
import os
import re
import secrets
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def ensure_env_file() -> None:
    """.env 가 없거나 관리자 비밀번호가 비어 있으면 처음 한 번 물어서 만들어 둔다."""
    env = HERE / ".env"
    text = env.read_text(encoding="utf-8") if env.exists() else (HERE / ".env.example").read_text(encoding="utf-8")
    if re.search(r"^ADMIN_PASSWORD=\S", text, re.M) or os.environ.get("ADMIN_PASSWORD"):
        return
    if not sys.stdin or not sys.stdin.isatty():
        print("※ ADMIN_PASSWORD 가 설정되지 않아 관리자 화면에 로그인할 수 없습니다. .env 파일을 확인하세요.")
        return
    print("관리자 화면(/admin)에서 쓸 비밀번호를 정해주세요. (입력한 글자는 화면에 보이지 않습니다)")
    while True:
        pw = getpass.getpass("  비밀번호: ").strip()
        if len(pw) < 4:
            print("  4자 이상 입력해주세요.")
            continue
        if getpass.getpass("  한 번 더: ").strip() != pw:
            print("  두 번 입력한 값이 다릅니다.")
            continue
        break
    text = re.sub(r"^ADMIN_PASSWORD=.*$", lambda _: f"ADMIN_PASSWORD={pw}", text, flags=re.M)
    if re.search(r"^SECRET_KEY=\s*$", text, re.M):
        text = re.sub(r"^SECRET_KEY=\s*$", f"SECRET_KEY={secrets.token_hex(32)}", text, flags=re.M)
    env.write_text(text, encoding="utf-8")
    print(f"  저장했습니다: {env}\n  (비밀번호를 바꾸려면 이 파일의 ADMIN_PASSWORD 를 고친 뒤 다시 실행하세요)\n")


if __name__ == "__main__":
    # 어느 폴더에서 실행해도 이 폴더의 .env 와 queue.db 를 사용
    os.chdir(HERE)
    sys.path.insert(0, str(HERE))
    ensure_env_file()

    import uvicorn

    from app import config
    from app.netinfo import lan_ip

    port = int(os.environ.get("PORT", "8000"))
    base = config.PUBLIC_URL.rstrip("/") if config.PUBLIC_URL else f"http://{lan_ip()}:{port}"
    print("=" * 56)
    print(f"  손님 접수      {base}/")
    print(f"  현황판(TV)     {base}/board")
    print(f"  관리자         {base}/admin")
    print(f"  (이 PC에서는   http://localhost:{port}/ 로도 열 수 있음)")
    print("  종료하려면 이 창에서 Ctrl+C")
    print("=" * 56)

    uvicorn.run(
        "app.main:app",
        host=os.environ.get("HOST", "0.0.0.0"),
        port=port,
        # SSE 연결이 열려 있어도 Ctrl+C 시 빨리 종료되도록
        timeout_graceful_shutdown=2,
        proxy_headers=True,
    )
