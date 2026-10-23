"""u32 length | u8 type | CBOR, 4 MiB max."""

from __future__ import annotations

import struct
from asyncio import StreamReader

MAX_FRAME = 4 * 1024 * 1024


class FrameError(ValueError):
    pass


def encode_frame(msg_type: int, payload: bytes) -> bytes:
    if msg_type < 0 or msg_type > 255:
        raise FrameError("bad type")
    body = bytes([msg_type]) + payload
    if len(body) > MAX_FRAME:
        raise FrameError("frame too large")
    return struct.pack(">I", len(body)) + body


def decode_frame(data: bytes) -> tuple[int, bytes]:
    if len(data) < 5:
        raise FrameError("short frame")
    (n,) = struct.unpack(">I", data[:4])
    if n > MAX_FRAME or n < 1:
        raise FrameError("bad length")
    if len(data) < 4 + n:
        raise FrameError("truncated")
    body = data[4 : 4 + n]
    return body[0], body[1:]


async def read_frame(reader: StreamReader) -> tuple[int, bytes]:
    hdr = await reader.readexactly(4)
    (n,) = struct.unpack(">I", hdr)
    if n > MAX_FRAME or n < 1:
        raise FrameError("bad length")
    body = await reader.readexactly(n)
    return body[0], body[1:]
