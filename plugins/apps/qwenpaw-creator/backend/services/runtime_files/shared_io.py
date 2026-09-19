# -*- coding: utf-8 -*-
"""Windows sharing semantics for atomic snapshot records."""

from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path
from typing import BinaryIO


@lru_cache(maxsize=1)
def _windows_api():
    import ctypes
    from ctypes import wintypes

    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    api.CreateFileW.restype = wintypes.HANDLE
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    api.ReplaceFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.LPVOID,
    ]
    api.ReplaceFileW.restype = wintypes.BOOL
    return api


def open_shared_read(path: Path) -> BinaryIO:
    """Read an existing inode while allowing writers to replace its name.

    CPython's normal Windows open does not include FILE_SHARE_DELETE.
    Polling readers can therefore starve os.replace despite using no lock.
    Keep the usual read/write sharing and additionally permit rename/delete;
    an already-open reader retains its complete old snapshot.
    """

    if os.name != "nt":
        return path.open("rb")
    import ctypes
    import msvcrt

    filename = str(path)
    if "\x00" in filename:
        raise ValueError("embedded null character in path")
    api = _windows_api()
    handle = api.CreateFileW(
        filename,
        0x80000000,  # GENERIC_READ
        0x00000001 | 0x00000002 | 0x00000004,  # READ | WRITE | DELETE sharing
        None,  # Non-inheritable handle; preserve the existing file's ACL.
        3,  # OPEN_EXISTING
        0x80,  # FILE_ATTRIBUTE_NORMAL
        None,
    )
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        descriptor = msvcrt.open_osfhandle(
            handle,
            os.O_RDONLY | os.O_BINARY | os.O_NOINHERIT,
        )
    except BaseException:
        api.CloseHandle(handle)
        raise
    # The CRT descriptor now owns the handle, including on fdopen failure.
    try:
        return os.fdopen(descriptor, "rb")
    except BaseException:
        os.close(descriptor)
        raise


def replace_open_file(source: Path, target: Path) -> None:
    """Replace an existing Windows file whose readers share delete access.

    MoveFileEx (os.replace) still rejects an open destination. ReplaceFileW
    supports the shared handles while preserving the destination's ACL.
    The caller keeps os.replace for creation and directory publication.
    """

    import ctypes

    if not _windows_api().ReplaceFileW(
        str(target),
        str(source),
        None,
        0,
        None,
        None,
    ):
        raise ctypes.WinError(ctypes.get_last_error())
