import datetime
import re
from pathlib import Path

INVALID_FILENAME_CHARS = r'\\/:*?"<>|'


def safe_filename(name: str, max_len: int = 50) -> str:
    # Reemplaza multiples espacios por '-', quita caracteres invalidos, limita longitud
    s = name.strip()
    s = re.sub(r"\s+", "-", s)
    s = "".join(ch for ch in s if ch not in INVALID_FILENAME_CHARS)
    if len(s) > max_len:
        s = s[:max_len]
    # Remove leading/trailing hyphens
    s = s.strip("-")
    return s or "untitled"


def ensure_dir(path: str):
    Path(path).mkdir(parents=True, exist_ok=True)


def formatted_timestamp_for_filename(dt: datetime.datetime) -> str:
    return dt.strftime("%Y%m%d-%H%M%S")


def formatted_timestamp_for_filecontent(dt: datetime.datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


