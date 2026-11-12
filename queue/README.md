# 매장 대기 순번 시스템

손님이 매장의 QR코드를 찍으면 휴대폰 브라우저로 대기번호를 받고, 관리자는 `/admin` 화면에서 호출·완료를 처리합니다. 앱을 설치할 필요가 없습니다.

- 손님 화면: `http://서버주소:8000/`
- 관리자 화면: `http://서버주소:8000/admin`

> 이 폴더는 GitHub Pages(정적 사이트)에서는 실행되지 않습니다. 아래처럼 PC나 서버에서 직접 실행해야 합니다.

## 1. 설치 (처음 한 번)

Python 3.10 이상이 필요합니다. `queue` 폴더에서 실행합니다.

```bash
python -m venv .venv
```

```bash
.venv\Scripts\activate
```
(macOS/Linux: `source .venv/bin/activate`)

```bash
pip install -r requirements.txt
```

## 2. 관리자 비밀번호 설정

`.env.example` 파일을 복사해서 `.env` 파일을 만들고 값을 바꿉니다.

```bash
copy .env.example .env
```

| 항목 | 설명 |
|---|---|
| `ADMIN_PASSWORD` | **필수.** 관리자 로그인 비밀번호. 비어 있으면 관리자 화면에 로그인할 수 없습니다. |
| `SECRET_KEY` | 로그인 상태 유지용 비밀키. 비워두면 서버를 재시작할 때마다 다시 로그인해야 합니다. `python -c "import secrets; print(secrets.token_hex(32))"` 로 만들어 넣으세요. |
| `STORE_NAME` | 화면 상단에 표시할 이름 |
| `RETENTION_DAYS` | 이 일수가 지난 접수의 이름·전화번호 뒷자리를 자동으로 지웁니다(기본 30일). 통계용 숫자는 남습니다. |
| `DATABASE_URL` | 기본은 이 폴더의 `queue.db` (SQLite) |

`.env` 와 `queue.db` 는 git에 올라가지 않도록 `.gitignore` 에 들어 있습니다. 비밀번호를 바꾼 뒤에는 서버를 다시 시작하세요.

## 3. 실행

```bash
python run.py
```

- 같은 PC에서는 `http://localhost:8000` 으로 열립니다.
- 손님 휴대폰은 **같은 와이파이**에 연결된 상태에서 `http://PC의IP:8000` 으로 접속합니다. PC의 IP는 `ipconfig` 의 "IPv4 주소"로 확인합니다.
- Windows 방화벽 창이 뜨면 "개인 네트워크"에서 허용해주세요.
- 종료는 `Ctrl+C` 입니다.

## 4. QR코드 만들기

```bash
python scripts/make_qr.py http://192.168.0.10:8000/ -o 매장QR.png
```

주소는 실제 손님이 접속할 주소로 바꾸세요. PC의 IP가 바뀌면(공유기 재시작 등) QR코드도 다시 만들어야 하니, 공유기에서 PC에 고정 IP를 지정해두는 것을 권장합니다.

## 5. 사용 방법

**손님**
1. QR코드 스캔 → 이름(한글 2~4자)과 전화번호 뒷 4자리 입력 → 대기번호 발급
2. 내 번호 화면에서 대기 순서 확인. **"호출 알림 소리·진동 켜기"** 를 한 번 눌러두면 호출 시 소리와 진동이 울립니다. 휴대폰 브라우저는 사용자가 화면을 한 번 눌러야 소리를 낼 수 있습니다. iPhone은 진동을 지원하지 않습니다.
3. 화면을 닫았다가 다시 QR을 찍거나 주소를 열어도 내 번호 화면으로 돌아옵니다.

**관리자**
- **호출**: 손님 화면이 주황색으로 바뀌고 알림이 울립니다.
- **완료**: 처리 완료. 대기 목록에서 내려갑니다.
- **노쇼 / 건너뛰기**: 호출 후 오지 않는 손님을 처리합니다(호출 전이면 "건너뛰기").
- **되돌리기**: "오늘 처리 내역"에서 실수로 처리한 손님을 대기 목록으로 되돌립니다.
- **접수 마감하기 / 재개하기**: 마감 중에는 손님 화면에 마감 안내가 나오고 새 접수가 막힙니다.

대기번호는 매일 자정(한국 시간)에 1번부터 다시 시작합니다.

## 6. 개인정보

- 손님 화면에는 이름이 가려져서(김○수) 표시되고, 전화번호는 아예 보내지 않습니다. 원본은 관리자 화면에서만 보입니다.
- `RETENTION_DAYS` 가 지난 기록은 서버가 켜져 있는 동안 6시간마다 자동으로 이름·전화번호를 지웁니다(서버 시작 시에도 1회 실행).

## 7. 인터넷에 공개하려면

매장 와이파이 밖에서도 접속하게 하려면 Render, Fly.io, 클라우드 VM 같은 곳에 올리고 **HTTPS** 로 서비스하세요. 이때 다음 사항을 지켜야 합니다.
- 시작 명령: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --timeout-graceful-shutdown 2`
- 환경변수 `ADMIN_PASSWORD`, `SECRET_KEY` 를 호스팅 설정 화면에서 지정
- SQLite 파일이 재배포 때 지워지지 않도록 영구 디스크를 쓰거나 PostgreSQL(`DATABASE_URL`)로 전환
- 실시간 알림(SSE)이 메모리 기반이라 **서버 프로세스는 1개**로 실행하세요(workers 1).

## 8. 테스트

```bash
python -m pytest -q
```

## 폴더 구조

```
app/
  main.py       라우트(손님·관리자·SSE)
  services.py   접수·검증·마스킹·상태변경·통계·개인정보 삭제
  models.py     DB 테이블 (queue_entries, settings)
  db.py         DB 연결 (SQLite 동시 접수 잠금 처리)
  auth.py       관리자 로그인 쿠키 · CSRF
  events.py     실시간 변경 알림(SSE)
  templates/    화면 HTML
  static/       CSS, JS, 로고
scripts/make_qr.py   QR코드 생성
run.py               실행 스크립트
tests/               자동 테스트
```
