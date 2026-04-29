"""Cache utilities for office-anonymizer: XDG-aware base dir + janitor sweep.

Design contract:
- resolve_cache_base() returns a deterministic path. No platformdirs dependency.
- mkdtemp_run() creates a unique 0700 run directory under the cache base.
- write_expires_at() stores a sentinel timestamp; janitor_sweep() enforces it.
- janitor_sweep() also removes orphan run dirs older than DEFAULT_MAX_AGE_DAYS.
- set_mode_0600(path) is a thin helper for single-file artifacts.

The sweep and permissions are security-relevant: candidate summaries and codex
logs contain raw-identifier context and must never leak onto a shared disk.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


DEFAULT_RETENTION_DAYS = 14
DEFAULT_MAX_AGE_DAYS = 30
_EXPIRES_AT_SENTINEL = "expires_at"


def resolve_cache_base() -> Path:
    """Deterministic, platform-aware cache base for office-anonymizer artifacts.

    Resolution order (first match wins):
      1. $XDG_CACHE_HOME/office-anonymizer       (absolute path required)
      2. macOS:   ~/Library/Caches/office-anonymizer
      3. Windows: %LOCALAPPDATA%\\office-anonymizer (or AppData/Local fallback)
      4. Other:   ~/.cache/office-anonymizer
    """
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg and Path(xdg).is_absolute():
        return Path(xdg) / "office-anonymizer"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "office-anonymizer"
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        base = Path(local) if local else Path.home() / "AppData" / "Local"
        return base / "office-anonymizer"
    return Path.home() / ".cache" / "office-anonymizer"


def ensure_cache_base() -> Path:
    base = resolve_cache_base()
    base.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(base, 0o700)
    except PermissionError:
        pass
    return base


def mkdtemp_run(prefix: str = "oa-") -> Path:
    """Create a unique run directory inside the cache base, chmod 0700."""
    base = ensure_cache_base()
    path = Path(tempfile.mkdtemp(prefix=prefix, dir=str(base)))
    os.chmod(path, 0o700)
    return path


def write_expires_at(run_dir: Path, days: int = DEFAULT_RETENTION_DAYS) -> Path:
    """Record an expiry timestamp sentinel inside a run dir.

    The file only records *intent*. janitor_sweep() is what actually enforces it
    on the next invocation.
    """
    expiry = datetime.now(timezone.utc) + timedelta(days=days)
    sentinel = run_dir / _EXPIRES_AT_SENTINEL
    sentinel.write_text(expiry.isoformat(), encoding="utf-8")
    os.chmod(sentinel, 0o600)
    return sentinel


def set_mode_0600(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except (FileNotFoundError, PermissionError):
        pass


def janitor_sweep(max_age_days: int = DEFAULT_MAX_AGE_DAYS) -> list[Path]:
    """Remove run dirs that have expired or are older than max_age_days.

    Called at the top of every skill invocation. Never raises; best-effort
    cleanup for a path the user might not own.
    """
    base = resolve_cache_base()
    if not base.exists():
        return []
    removed: list[Path] = []
    now = datetime.now(timezone.utc)
    cutoff_mtime = time.time() - (max_age_days * 86400)
    for entry in base.iterdir():
        if not entry.is_dir():
            continue
        if _is_expired(entry, now=now) or entry.stat().st_mtime < cutoff_mtime:
            try:
                shutil.rmtree(entry, ignore_errors=True)
                removed.append(entry)
            except OSError:
                continue
    return removed


def cleanup_runid(run_dir: Path) -> None:
    """Delete a specific run dir. Called at the end of a successful run."""
    if run_dir.exists():
        shutil.rmtree(run_dir, ignore_errors=True)


def _is_expired(run_dir: Path, *, now: datetime) -> bool:
    sentinel = run_dir / _EXPIRES_AT_SENTINEL
    if not sentinel.exists():
        return False
    try:
        stamp = datetime.fromisoformat(sentinel.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp <= now
