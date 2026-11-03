"""Cross-process single-instance guard for Domain Viewer."""

import ctypes
import os
import tempfile


WINDOWS_MUTEX_NAME = r"Local\etudetools.DomainViewer.SingleInstance"


class SingleInstanceMutex:
    """Own a named Windows mutex (or a file lock on POSIX) for this process."""

    def __init__(self):
        self._handle = None
        self._kernel32 = None
        self._lock_fd = None

    def acquire(self):
        if os.name == "nt":
            from ctypes import wintypes

            self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            create_mutex = self._kernel32.CreateMutexW
            create_mutex.argtypes = [
                wintypes.LPVOID,
                wintypes.BOOL,
                wintypes.LPCWSTR,
            ]
            create_mutex.restype = wintypes.HANDLE

            self._kernel32.ReleaseMutex.argtypes = [wintypes.HANDLE]
            self._kernel32.ReleaseMutex.restype = wintypes.BOOL
            self._kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            self._kernel32.CloseHandle.restype = wintypes.BOOL

            ctypes.set_last_error(0)
            handle = create_mutex(None, True, WINDOWS_MUTEX_NAME)
            if not handle:
                raise ctypes.WinError(ctypes.get_last_error())

            if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
                self._kernel32.CloseHandle(handle)
                return False

            self._handle = handle
            return True

        # Keep development/test runs on macOS and Linux single-instance too.
        import fcntl

        lock_path = os.path.join(tempfile.gettempdir(), "DomainViewer.instance.lock")
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            return False

        self._lock_fd = fd
        return True

    def release(self):
        if self._handle:
            try:
                self._kernel32.ReleaseMutex(self._handle)
            finally:
                self._kernel32.CloseHandle(self._handle)
                self._handle = None

        if self._lock_fd is not None:
            try:
                import fcntl
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(self._lock_fd)
                self._lock_fd = None
