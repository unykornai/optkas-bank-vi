"""
Windows-safe icon map
======================
Windows legacy consoles (cp1252) cannot render emoji.
This module detects the encoding and falls back to ASCII.
"""

from __future__ import annotations

import os
import sys

def _can_render_emoji() -> bool:
    """Return True if stdout can handle emoji characters."""
    if os.environ.get("PYTHONIOENCODING", "").lower().startswith("utf"):
        return True
    try:
        encoding = sys.stdout.encoding or ""
        if encoding.lower().replace("-", "") in ("utf8", "utf16", "utf32"):
            return True
    except Exception:
        pass
    return False


_EMOJI = _can_render_emoji()

# ---- Grade / severity icons ----
ICON_CLEAR      = "\u2705" if _EMOJI else "[OK]"       # ✅
ICON_QUALIFIED  = "\u26a0\ufe0f" if _EMOJI else "[!!]" # ⚠️
ICON_ADVERSE    = "\U0001f6ab" if _EMOJI else "[XX]"    # 🚫
ICON_UNABLE     = "\u2753" if _EMOJI else "[??]"        # ❓
ICON_INFO       = "\u2139\ufe0f" if _EMOJI else "[ii]"  # ℹ️

# ---- Severity bullets ----
ICON_CRITICAL   = "\U0001f534" if _EMOJI else "[!!]"    # 🔴
ICON_HIGH       = "\U0001f7e0" if _EMOJI else "[!]"     # 🟠
ICON_MEDIUM     = "\U0001f7e1" if _EMOJI else "[-]"     # 🟡

# ---- Misc ----
ICON_FOLDER     = "\U0001f4c1" if _EMOJI else "[D]"     # 📁
ICON_ALERT      = "\U0001f6a8" if _EMOJI else "[!!]"    # 🚨
ICON_CHECK      = "\u2713"     if _EMOJI else "[v]"     # ✓
ICON_CROSS      = "\u2717"     if _EMOJI else "[x]"     # ✗
ICON_WARN       = "\u26a0\ufe0f" if _EMOJI else "[!]"   # ⚠️
ICON_BLOCK      = "\U0001f6ab" if _EMOJI else "[X]"     # 🚫

# ---- Lookup helpers ----

GRADE_ICONS: dict[str, str] = {
    "CLEAR": ICON_CLEAR,
    "QUALIFIED": ICON_QUALIFIED,
    "ADVERSE": ICON_ADVERSE,
    "UNABLE_TO_OPINE": ICON_UNABLE,
}

SEVERITY_ICONS: dict[str, str] = {
    "CRITICAL": ICON_CRITICAL,
    "HIGH": ICON_HIGH,
    "MEDIUM": ICON_MEDIUM,
    "ERROR": ICON_ADVERSE,
    "WARNING": ICON_WARN,
    "INFO": ICON_INFO,
}

RED_FLAG_ICONS: dict[str, str] = {
    "CRITICAL": ICON_CRITICAL,
    "HIGH": ICON_HIGH,
    "MEDIUM": ICON_MEDIUM,
}
