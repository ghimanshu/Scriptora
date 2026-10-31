import socket
import struct

from app.core.config import get_settings


def scan(data: bytes) -> bool:
    cfg = get_settings()
    if cfg.scanner_driver == "bypass":
        if cfg.app_env == "production":
            raise RuntimeError("Scanner bypass forbidden")
        return True
    with socket.create_connection((cfg.scanner_host, cfg.scanner_port), timeout=30) as conn:
        conn.sendall(b"zINSTREAM\0")
        for offset in range(0, len(data), 65536):
            chunk = data[offset : offset + 65536]
            conn.sendall(struct.pack("!I", len(chunk)) + chunk)
        conn.sendall(struct.pack("!I", 0))
        result = bytearray()
        while b"\0" not in result:
            part = conn.recv(4096)
            if not part:
                break
            result.extend(part)
            if len(result) > 8192:
                raise RuntimeError("Invalid scanner response")
    if b"FOUND" in result:
        return False
    if b"OK" not in result:
        raise RuntimeError("Scanner unavailable or invalid response")
    return True
