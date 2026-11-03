"""Wait for the previous process to exit, then relaunch Domain Viewer."""

import os
import subprocess
import sys
import time
from pathlib import Path


def wait_for_process_exit(process_id):
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        open_process = kernel32.OpenProcess
        open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        open_process.restype = wintypes.HANDLE
        wait_for_single_object = kernel32.WaitForSingleObject
        wait_for_single_object.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        wait_for_single_object.restype = wintypes.DWORD
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        process_handle = open_process(0x00100000, False, int(process_id))
        if process_handle:
            try:
                wait_for_single_object(process_handle, 0xFFFFFFFF)
            finally:
                kernel32.CloseHandle(process_handle)
            return

    while True:
        try:
            os.kill(int(process_id), 0)
        except OSError:
            return
        time.sleep(0.2)


def main(argv):
    if len(argv) < 3:
        return 2

    old_process_id = int(argv[1])
    entry_script = Path(argv[2]).expanduser().resolve()
    extra_args = argv[3:]

    wait_for_process_exit(old_process_id)

    if getattr(sys, "frozen", False):
        command = [sys.executable]
    else:
        command = [sys.executable, str(entry_script)]
    command.extend(extra_args)

    creation_flags = 0
    if os.name == "nt":
        creation_flags = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )

    subprocess.Popen(
        command,
        cwd=str(entry_script.parent),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=creation_flags,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
