from __future__ import annotations

import ctypes
from ctypes import wintypes

SERVICE = "PolishMapAI/OpenAICompatible"
CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2


class CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME), ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)), ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR),
    ]


def set_api_key(value: str) -> None:
    blob = value.encode("utf-16-le")
    buffer = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
    cred = CREDENTIALW(Type=CRED_TYPE_GENERIC, TargetName=SERVICE,
                       CredentialBlobSize=len(blob), CredentialBlob=buffer,
                       Persist=CRED_PERSIST_LOCAL_MACHINE, UserName="PolishMapAI")
    if not ctypes.windll.advapi32.CredWriteW(ctypes.byref(cred), 0):
        raise ctypes.WinError()


def get_api_key() -> str:
    ptr = ctypes.POINTER(CREDENTIALW)()
    if not ctypes.windll.advapi32.CredReadW(SERVICE, CRED_TYPE_GENERIC, 0, ctypes.byref(ptr)):
        return ""
    try:
        cred = ptr.contents
        return ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize).decode("utf-16-le")
    finally:
        ctypes.windll.advapi32.CredFree(ptr)

