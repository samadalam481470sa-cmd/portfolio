"""asyncio TCP transport with length-prefixed frames."""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from clearmesh.p2p.framing import encode_frame, read_frame


class TcpTransport:
    def __init__(
        self,
        on_message: Callable[[str, int, bytes], Awaitable[None] | None],
    ) -> None:
        self.on_message = on_message
        self._server: asyncio.Server | None = None
        self._peers: dict[str, tuple[asyncio.StreamReader, asyncio.StreamWriter]] = {}

    async def start_server(self, host: str, port: int) -> None:
        self._server = await asyncio.start_server(self._accept, host, port)

    async def _accept(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer = f"{writer.get_extra_info('peername')}"
        self._peers[peer] = (reader, writer)
        try:
            while True:
                mtype, payload = await asyncio.wait_for(read_frame(reader), timeout=30)
                res = self.on_message(peer, mtype, payload)
                if asyncio.iscoroutine(res):
                    await res
        except Exception:  # noqa: BLE001
            pass
        finally:
            self._peers.pop(peer, None)
            writer.close()

    async def connect(self, host: str, port: int) -> str:
        reader, writer = await asyncio.open_connection(host, port)
        peer = f"{host}:{port}"
        self._peers[peer] = (reader, writer)
        asyncio.create_task(self._read_loop(peer, reader, writer))
        return peer

    async def _read_loop(
        self, peer: str, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            while True:
                mtype, payload = await asyncio.wait_for(read_frame(reader), timeout=30)
                res = self.on_message(peer, mtype, payload)
                if asyncio.iscoroutine(res):
                    await res
        except Exception:  # noqa: BLE001
            pass
        finally:
            self._peers.pop(peer, None)
            writer.close()

    async def send(self, peer: str, msg_type: int, payload: bytes) -> None:
        pair = self._peers.get(peer)
        if not pair:
            return
        _, writer = pair
        writer.write(encode_frame(msg_type, payload))
        await writer.drain()

    async def broadcast(self, msg_type: int, payload: bytes) -> None:
        for peer in list(self._peers):
            await self.send(peer, msg_type, payload)

    async def close(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        for _, w in list(self._peers.values()):
            w.close()
