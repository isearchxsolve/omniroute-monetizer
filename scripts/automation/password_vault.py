#!/usr/bin/env python3
"""
Windows DPAPI (Data Protection API) Password Vault.
Encrypts and decrypts secrets using CryptProtectData and CryptUnprotectData via ctypes.
Redacts plaintext from disk and keeps secrets protected by Windows user logon credentials.
"""
import os
import sys
import ctypes
from ctypes import wintypes
from pathlib import Path

# Windows Crypt32 types
class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte))
    ]

crypt32 = ctypes.windll.crypt32
kernel32 = ctypes.windll.kernel32

def protect_data(plaintext: str) -> bytes:
    """Encrypt a plaintext string using Windows DPAPI at MACHINE scope.

    Uses CRYPTPROTECT_LOCAL_MACHINE (0x4) so the blob is decryptable by any
    local principal (SYSTEM services AND interactive users). This fixes the
    cross-principal failure where a SYSTEM-written user-scoped blob could not
    be decrypted by an interactive Admin session (and vice versa).
    CRYPTPROTECT_UI_FORBIDDEN (0x1) suppresses any UI prompt.
    """
    data_bytes = plaintext.encode("utf-8")
    blob_in = DATA_BLOB()
    blob_in.cbData = len(data_bytes)
    blob_in.pbData = ctypes.cast(ctypes.create_string_buffer(data_bytes, len(data_bytes)), ctypes.POINTER(ctypes.c_byte))
    
    blob_out = DATA_BLOB()
    
    # CryptProtectData(pDataIn, szDataDescr, pOptionalEntropy, pvReserved, pPromptStruct, dwFlags, pDataOut)
    # dwFlags = CRYPTPROTECT_UI_FORBIDDEN (0x1) | CRYPTPROTECT_LOCAL_MACHINE (0x4)
    flags = 0x1 | 0x4
    res = crypt32.CryptProtectData(
        ctypes.byref(blob_in),
        "omniroute-monetizer-vault",
        None,
        None,
        None,
        flags,
        ctypes.byref(blob_out)
    )
    if not res:
        raise OSError("CryptProtectData failed to encrypt data with Windows DPAPI.")
    
    try:
        encrypted_bytes = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        return encrypted_bytes
    finally:
        kernel32.LocalFree(blob_out.pbData)

def unprotect_data(encrypted_bytes: bytes) -> str:
    """Decrypt ciphertext bytes using Windows DPAPI.

    Tries MACHINE scope first (0x4), then falls back to USER scope (0x1) for
    backward compatibility with legacy user-scoped blobs.
    """
    for flags in (0x1 | 0x4, 0x1):
        blob_in = DATA_BLOB()
        blob_in.cbData = len(encrypted_bytes)
        blob_in.pbData = ctypes.cast(ctypes.create_string_buffer(encrypted_bytes, len(encrypted_bytes)), ctypes.POINTER(ctypes.c_byte))
        
        blob_out = DATA_BLOB()
        res = crypt32.CryptUnprotectData(
            ctypes.byref(blob_in),
            None,
            None,
            None,
            None,
            flags,
            ctypes.byref(blob_out)
        )
        if res:
            try:
                decrypted_bytes = ctypes.string_at(blob_out.pbData, blob_out.cbData)
                return decrypted_bytes.decode("utf-8")
            finally:
                kernel32.LocalFree(blob_out.pbData)
    raise OSError("CryptUnprotectData failed to decrypt data with Windows DPAPI (machine and user scope).")

def store_password(password: str, vault_path: Path = None) -> Path:
    """Encrypt and store password in DPAPI vault."""
    if vault_path is None:
        vault_path = Path(__file__).resolve().parent.parent.parent / "state" / "omniroute_password.bin"
    vault_path.parent.mkdir(parents=True, exist_ok=True)
    encrypted = protect_data(password)
    with open(vault_path, "wb") as f:
        f.write(encrypted)
    return vault_path

def retrieve_password(vault_path: Path = None) -> str:
    """Retrieve and decrypt password from DPAPI vault."""
    if vault_path is None:
        vault_path = Path(__file__).resolve().parent.parent.parent / "state" / "omniroute_password.bin"
    if not vault_path.exists():
        raise FileNotFoundError(f"Vault file not found at {vault_path}")
    with open(vault_path, "rb") as f:
        encrypted = f.read()
    return unprotect_data(encrypted)

if __name__ == "__main__":
    # Test encryption roundtrip
    test_str = "dpapi-test-pass-12345"
    enc = protect_data(test_str)
    dec = unprotect_data(enc)
    assert test_str == dec, "DPAPI roundtrip mismatch!"
    print("[+] Windows DPAPI CryptProtectData/CryptUnprotectData verified successfully.")
