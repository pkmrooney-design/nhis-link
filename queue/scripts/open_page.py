"""바탕화면 바로가기에서 실행: 서버가 꺼져 있으면 켜고, 브라우저로 화면을 연다.

사용법:  pythonw scripts/open_page.py [board|admin]
"""

import re
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
PORT = 8000
PAGES = {"": "", "board": "board", "admin": "admin"}


def server_up() -> bool:
    try:
        urllib.request.urlopen(f"http://localhost:{PORT}/api/queue", timeout=2)
        return True
    except Exception:
        return False


def start_server() -> None:
    env = HERE / ".env"
    ready = (HERE / ".venv" / ".installed").exists() and env.exists() and re.search(
        r"^ADMIN_PASSWORD=\S", env.read_text(encoding="utf-8"), re.M
    )
    info = subprocess.STARTUPINFO()
    if ready:
        # 설정이 끝난 상태면 서버 창을 최소화해서 띄움 (처음이면 비밀번호를 물어야 하니 그대로 보여줌)
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow = 7  # SW_SHOWMINNOACTIVE
    subprocess.Popen(
        ["cmd", "/c", str(HERE / "start.bat")],
        cwd=HERE,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
        startupinfo=info,
    )


def main() -> None:
    page = PAGES.get(sys.argv[1] if len(sys.argv) > 1 else "", "")
    if not server_up():
        start_server()
        # 처음 실행이면 설치·비밀번호 입력까지 기다림 (최대 10분)
        for _ in range(600):
            if server_up():
                break
            time.sleep(1)
    webbrowser.open(f"http://localhost:{PORT}/{page}")


if __name__ == "__main__":
    main()
