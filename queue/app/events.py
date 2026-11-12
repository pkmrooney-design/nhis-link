"""SSE 로 '목록이 바뀌었다' 신호만 보낸다. 화면은 신호를 받으면 자기 데이터를 다시 받아온다.

서버 프로세스 하나 기준의 메모리 방식이라 여러 프로세스로 띄우면 다른 프로세스의 변경은
알 수 없다(그래도 화면이 5초 폴링으로 보완함).
"""

import asyncio


class Broadcaster:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._event = asyncio.Event()

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def _fire(self) -> None:
        ev, self._event = self._event, asyncio.Event()
        ev.set()

    def notify(self) -> None:
        """어느 스레드에서 불러도 안전 (동기 라우트는 스레드풀에서 실행됨)."""
        if self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._fire)

    async def wait(self, timeout: float) -> bool:
        ev = self._event
        try:
            await asyncio.wait_for(ev.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            return False


broadcaster = Broadcaster()
