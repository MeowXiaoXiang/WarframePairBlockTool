"""透過 Qt 本機通訊喚出已執行的主視窗。"""

import ctypes
import sys

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


SERVER_NAME = "WarframePairBlockTool-single-instance"


def notify_existing(timeout_ms=500):
    socket = QLocalSocket()
    socket.connectToServer(SERVER_NAME)
    if not socket.waitForConnected(timeout_ms):
        return False
    socket.write(b"show\n")
    socket.flush()
    socket.waitForBytesWritten(timeout_ms)
    socket.disconnectFromServer()
    return True


class SingleInstance(QObject):
    activate_requested = Signal()

    def __init__(self):
        super().__init__()
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self._receive)
        self._kernel32 = None
        self._mutex_handle = None

    def _acquire_mutex(self):
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_mutex = self._kernel32.CreateMutexW
        create_mutex.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)
        create_mutex.restype = ctypes.c_void_p
        self._kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
        self._kernel32.CloseHandle.restype = ctypes.c_bool
        handle = create_mutex(None, False, f"Local\\{SERVER_NAME}")
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            self._kernel32.CloseHandle(handle)
            return False
        self._mutex_handle = handle
        return True

    def acquire(self):
        if sys.platform == "win32" and not self._acquire_mutex():
            if notify_existing():
                return False
            raise RuntimeError("既有執行個體未回應，無法確認單一實例狀態")
        if self.server.listen(SERVER_NAME):
            return True
        if notify_existing():
            self.close()
            return False
        if sys.platform != "win32" and QLocalServer.removeServer(SERVER_NAME) and self.server.listen(SERVER_NAME):
            return True
        error = self.server.errorString()
        self.close()
        raise RuntimeError(error)

    def close(self):
        self.server.close()
        if self._mutex_handle:
            self._kernel32.CloseHandle(self._mutex_handle)
            self._mutex_handle = None

    def _receive(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            self.activate_requested.emit()
            socket.disconnectFromServer()
            socket.deleteLater()
