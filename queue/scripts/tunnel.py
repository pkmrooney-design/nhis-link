"""인터넷 주소 열기: 서버가 꺼져 있으면 켜고, Cloudflare 임시 터널로 https 주소를 만든다.

사용법:  tunnel.bat 더블클릭 (또는 .venv\\Scripts\\python scripts\\tunnel.py)
- 이 창이 켜져 있는 동안만 인터넷 주소가 열린다. 닫으면 주소도 사라진다.
- 다시 열 때마다 주소가 바뀐다.
"""

import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from open_page import HERE, PORT, server_up, start_server  # noqa: E402

CLOUDFLARED = HERE / "tools" / "cloudflared.exe"
URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def main() -> None:
    if not CLOUDFLARED.exists():
        raise SystemExit(
            f"{CLOUDFLARED} 가 없습니다.\n"
            "https://github.com/cloudflare/cloudflared/releases 에서 cloudflared-windows-amd64.exe 를 받아\n"
            "tools 폴더에 cloudflared.exe 라는 이름으로 넣어주세요."
        )
    if not server_up():
        print("서버를 켜는 중...")
        start_server()
        for _ in range(600):
            if server_up():
                break
            time.sleep(1)

    print("인터넷 주소를 만드는 중... (10초 정도 걸립니다)")
    proc = subprocess.Popen(
        [str(CLOUDFLARED), "tunnel", "--no-autoupdate", "--url", f"http://localhost:{PORT}"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
    )
    shown = False
    try:
        for line in proc.stdout:
            m = URL_RE.search(line)
            if m and not shown:
                base = m.group(0)
                shown = True
                print("=" * 64)
                print("  담당자에게 보낼 주소 (어디서나 열림)")
                print(f"  손님 접수      {base}/")
                print(f"  현황판(TV)     {base}/board")
                print(f"  관리자         {base}/admin")
                print("  이 창을 닫으면 위 주소는 더 이상 열리지 않습니다.")
                print("  (주소가 처음 열리기까지 30초 정도 걸릴 수 있습니다)")
                print("=" * 64)
    except KeyboardInterrupt:
        pass
    finally:
        proc.terminate()


if __name__ == "__main__":
    main()
