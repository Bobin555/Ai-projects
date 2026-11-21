"""Block all outbound network access while an offline pack runs."""
from __future__ import annotations

import socket
from contextlib import contextmanager
from typing import Iterator

# Everything that can reach another machine without connect(): name lookups and unconnected (UDP) sends.
_BLOCKED = ((socket, "create_connection"), (socket, "getaddrinfo"), (socket, "gethostbyname"),
            (socket, "gethostbyname_ex"), (socket, "gethostbyaddr"), (socket, "getnameinfo"),
            (socket.socket, "connect"), (socket.socket, "connect_ex"), (socket.socket, "sendto"),
            (socket.socket, "sendmsg"))


class NetworkBlocked(RuntimeError):
    """Raised when code tries to reach the network inside no_network()."""


@contextmanager
def no_network() -> Iterator[None]:
    def blocked(*args, **kwargs):
        raise NetworkBlocked("network access is disabled for this pack")

    saved = [(owner, name, getattr(owner, name)) for owner, name in _BLOCKED]
    for owner, name, _ in saved:
        setattr(owner, name, blocked)
    try:
        yield
    finally:
        for owner, name, original in saved:
            setattr(owner, name, original)
