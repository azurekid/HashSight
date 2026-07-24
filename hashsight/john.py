"""Mapping helpers from hashcat-centric signatures to John the Ripper formats.

The bundled `signatures.json` is now the primary source of truth for `john_format`.
This module therefore keeps only:
    - a small mode->john fallback map for legacy/custom signature packs that may
        omit `john_format`, and
    - conservative name/category heuristics when mode-only mapping is unavailable.
"""
from __future__ import annotations

from typing import Optional


_MODE_TO_JOHN: dict[int, str] = {
    # Intentionally empty in the bundled project: john_format now lives in
    # signatures.json to avoid duplicated sources of truth.
    # Kept as an extension point for custom signature packs.
}


def _truecrypt_veracrypt_format(name: str) -> Optional[str]:
    if "veracrypt" in name:
        return "VeraCrypt"
    if "truecrypt" in name:
        if "ripemd160" in name or "ripemd-160" in name:
            return "tc_ripemd160"
        if "sha512" in name:
            return "tc_sha512"
        if "whirlpool" in name:
            return "tc_whirlpool"
    return None


def john_format_for(mode: Optional[int], name: Optional[str], category: Optional[str]) -> Optional[str]:
    """Return a conservative John format label when confidently known.

    This intentionally prefers under-reporting over wrong mapping.
    """
    if mode is not None and mode in _MODE_TO_JOHN:
        return _MODE_TO_JOHN[mode]

    n = (name or "").lower()
    c = (category or "").lower()

    tc = _truecrypt_veracrypt_format(n)
    if tc:
        return tc

    if "luks" in n:
        return "luks"
    if "wpa" in n and "pmk" in n:
        return "wpapsk-pmk"
    if "wpa" in n:
        return "wpapsk"
    if "office" in n and "old" in n:
        return "oldoffice"
    if "office" in n:
        return "office"
    if "pdf" in n:
        return "pdf"
    if "7-zip" in n or "7z" in n:
        return "7z"
    if "rar5" in n:
        return "rar5"
    if "rar" in n:
        return "rar"
    if "pkzip" in n:
        return "pkzip"
    if "zip" in n:
        return "zip"
    if "bitcoin" in n:
        return "bitcoin"
    if "ethereum" in n and "presale" in n:
        return "ethereum-presale"
    if "ethereum" in n:
        return "ethereum"
    if "blockchain" in n:
        return "blockchain"
    if "electrum" in n:
        return "electrum"
    if "keepass" in n:
        return "keepass"
    if "bitwarden" in n:
        return "bitwarden"
    if "agilekeychain" in n or ("1password" in n and ("v3" in n or "agile" in n)):
        return "agilekeychain"
    if "cloudkeychain" in n or "1password" in n:
        return "cloudkeychain"
    if "password safe" in n or "pwsafe" in n:
        return "pwsafe"
    if "lastpass" in n:
        return "lastpass"
    if "bitlocker" in n:
        return "BitLocker"
    if "rakp" in n or "ipmi" in n:
        return "rakp"
    if "sip digest" in n or n == "sip":
        return "sip"
    if "mysql323" in n:
        return "mysql"
    if "mysql4" in n or "mysql5" in n:
        return "mysql-sha1"
    if "phpass" in n or "wordpress" in n or "phpbb3" in n:
        return "phpass"
    if "drupal" in n:
        return "drupal7"
    if "ntlm" in n:
        return "nt"
    if n.startswith("md5") or n == "md5":
        return "raw-md5"
    if n.startswith("sha1") or n == "sha1":
        return "raw-sha1"
    if n.startswith("sha512") or n == "sha512":
        return "raw-sha512"
    if "bcrypt" in n:
        return "bcrypt"
    if "drupal" in n:
        return "drupal7"
    if "kerberos" in c and "tgs" in n:
        return "krb5tgs"
    if "kerberos" in c and "as-rep" in n:
        return "krb5asrep"

    return None
