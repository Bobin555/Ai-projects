"""Block all outbound network access while an offline pack runs."""
from __future__ import annotations

import socket
from contextlib import contextmanager
from typing import Iterator


class NetworkBlocked(RuntimeError):
    """Raised when code tries to reach the network inside no_network()."""


@contextmanager
def no_network() -> Iterator[None]:
    def blocked(*args, **kwargs):
        raise NetworkBlocked("network access is disabled for this pack")

    saved = (socket.socket.connect, socket.socket.connect_ex, socket.create_connection, socket.getaddrinfo)
    socket.socket.connect = blocked
    socket.socket.connect_ex = blocked
    socket.create_connection = blocked
    socket.getaddrinfo = blocked
    try:
        yield
    finally:
        (socket.socket.connect, socket.socket.connect_ex,
         socket.create_connection, socket.getaddrinfo) = saved
