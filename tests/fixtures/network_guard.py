import socket

import pytest


@pytest.fixture(autouse=True)
def local_network_only(monkeypatch):
    def address_allowed(address):
        if not isinstance(address, tuple):
            return
        if address[0] != "127.0.0.1":
            raise AssertionError("Test attempted a connection outside IPv4 loopback")

    for name in ("connect", "connect_ex", "sendto", "bind"):
        original = getattr(socket.socket, name)

        def checked(sock, *args, original=original, name=name):
            if sock.family in (socket.AF_INET, socket.AF_INET6):
                address_allowed(args[-1])
            return original(sock, *args)

        monkeypatch.setattr(socket.socket, name, checked)

    getaddrinfo = socket.getaddrinfo

    def resolve(host, *args, **kwargs):
        address_allowed((host,))
        return getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
