"""예약 페이지 주소로 QR코드 PNG 를 만든다.

사용법:
    python scripts/make_qr.py http://192.168.0.10:8000/
    python scripts/make_qr.py https://내도메인/ -o 매장QR.png --size 12
"""

import argparse

import qrcode
from qrcode.constants import ERROR_CORRECT_M


def main() -> None:
    p = argparse.ArgumentParser(description="예약 페이지 QR코드 PNG 생성")
    p.add_argument("url", help="손님이 접속할 주소 (예: http://192.168.0.10:8000/)")
    p.add_argument("-o", "--output", default="queue-qr.png", help="저장할 파일 이름")
    p.add_argument("--size", type=int, default=10, help="한 칸 크기(px), 기본 10")
    args = p.parse_args()

    if not args.url.startswith(("http://", "https://")):
        p.error("주소는 http:// 또는 https:// 로 시작해야 합니다")

    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_M, box_size=args.size, border=4)
    qr.add_data(args.url)
    qr.make(fit=True)
    qr.make_image(fill_color="black", back_color="white").save(args.output)
    print(f"저장됨: {args.output}  ({args.url})")


if __name__ == "__main__":
    main()
