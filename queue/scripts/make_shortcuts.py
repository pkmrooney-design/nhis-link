"""바탕화면에 손님 접수·현황판·관리자 바로가기 3개를 만든다 (Windows).

사용법:  .venv\\Scripts\\python scripts\\make_shortcuts.py
바로가기를 더블클릭하면 서버가 꺼져 있을 때 자동으로 켜고 브라우저로 해당 화면을 연다.
"""

import base64
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
SHORTCUTS = [("대기순번 - 손님 접수", ""), ("대기순번 - 현황판(TV)", "board"), ("대기순번 - 관리자", "admin")]


def main() -> None:
    pythonw = HERE / ".venv" / "Scripts" / "pythonw.exe"
    if not pythonw.exists():
        raise SystemExit("먼저 start.bat 을 한 번 실행해 설치를 끝내주세요.")
    script = HERE / "scripts" / "open_page.py"
    lines = [
        "$ws = New-Object -ComObject WScript.Shell",
        "$desk = [Environment]::GetFolderPath('Desktop')",
    ]
    for name, page in SHORTCUTS:
        lines += [
            f"$s = $ws.CreateShortcut((Join-Path $desk '{name}.lnk'))",
            f"$s.TargetPath = '{pythonw}'",
            f"$s.Arguments = '\"{script}\" {page}'.Trim()",
            f"$s.WorkingDirectory = '{HERE}'",
            "$s.IconLocation = \"$env:SystemRoot\\System32\\shell32.dll,13\"",
            "$s.Save()",
            f"Write-Output (Join-Path $desk '{name}.lnk')",
        ]
    # PowerShell 5.1 이 한글 경로를 올바로 읽도록 UTF-16 으로 인코딩해 전달
    encoded = base64.b64encode("\n".join(lines).encode("utf-16-le")).decode()
    out = subprocess.run(
        ["powershell", "-NoProfile", "-EncodedCommand", encoded],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if out.returncode != 0:
        raise SystemExit(out.stderr)
    print("바탕화면에 바로가기를 만들었습니다.")


if __name__ == "__main__":
    main()
