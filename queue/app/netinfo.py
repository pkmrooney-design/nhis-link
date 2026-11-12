import socket

from . import config

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}


def lan_ip() -> str:
    """같은 와이파이의 휴대폰이 접속할 수 있는 이 PC의 IP. (UDP connect 는 실제로 패킷을 보내지 않음)"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def public_base_url(request_base_url: str, host: str, port: int | None) -> str:
    """손님 휴대폰이 접속할 주소. PUBLIC_URL 이 있으면 그 값을,
    서버 PC 에서 localhost 로 열었으면 localhost 대신 PC의 IP 를 사용한다."""
    if config.PUBLIC_URL:
        return config.PUBLIC_URL.rstrip("/") + "/"
    if host in LOCAL_HOSTS:
        return f"http://{lan_ip()}{f':{port}' if port else ''}/"
    return request_base_url
