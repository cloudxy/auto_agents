"""E5：pytest-socket 已安装；公网 connect 可被插件拦截。"""
import socket

import pytest


def test_pytest_socket_plugin_available():
    import pytest_socket

    assert hasattr(pytest_socket, "disable_socket")
    pytest_socket.disable_socket()
    try:
        with pytest.raises((OSError, Exception)):
            socket.socket().connect(("example.com", 80))
    finally:
        pytest_socket.enable_socket()
