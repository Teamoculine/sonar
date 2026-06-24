import configparser
import os
import re
from datetime import timedelta
from typing import Optional


def parse_idf_list(value: str) -> list[str]:
    value = value.strip()
    if value.startswith("(") and value.endswith(")"):
        value = value[1:-1]
    return [v.strip() for v in value.split(",") if v.strip()]


def load_config(path: str = "sonar.idf") -> configparser.ConfigParser:
    if not os.path.exists(path):
        raise SystemExit(f"Config file '{path}' not found. Create it from sonar.example.idf.")
    cfg = configparser.ConfigParser(inline_comment_prefixes=(";",))
    cfg.read(path)
    return cfg


_CFG = load_config()


def cget(section: str, key: str, fallback=None):
    return _CFG.get(section, key, fallback=fallback)


def clist(section: str, key: str, fallback=None) -> list[str]:
    val = _CFG.get(section, key, fallback=None)
    if val is None:
        return fallback or []
    return parse_idf_list(val)


def parse_duration(s: str) -> Optional[timedelta]:
    pattern = re.compile(r"(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?")
    match = pattern.fullmatch(s.strip().lower())
    if not match or not any(match.groups()):
        return None
    days = int(match.group(1) or 0)
    hours = int(match.group(2) or 0)
    minutes = int(match.group(3) or 0)
    seconds = int(match.group(4) or 0)
    delta = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
    if delta.total_seconds() <= 0 or delta > timedelta(days=28):
        return None
    return delta


def fmt_duration(delta: timedelta) -> str:
    total = int(delta.total_seconds())
    d, r = divmod(total, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    parts = []
    if d:
        parts.append(f"{d}d")
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    if s:
        parts.append(f"{s}s")
    return "".join(parts) or "0s"

