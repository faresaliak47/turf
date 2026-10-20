"""
core/logging_config.py — Application logging foundation.

Writes to database.paths.get_logs_dir() (already correctly resolved for
both source runs and the packaged Windows .exe — see database/paths.py's
docstring), so log files land next to the database instead of somewhere
relative to the current working directory.

USAGE
──────
    from core.logging_config import get_logger
    log = get_logger(__name__)
    log.info("Application started")
    log.error("Database write failed: %s", exc)

WHAT IS LOGGED
───────────────
Callers are expected to log:
  - application startup / shutdown
  - unexpected/unhandled errors
  - database failures
  - Excel import/export failures
  - authentication events (login success/failure — NEVER the password)

WHAT MUST NEVER BE LOGGED
───────────────────────────
Passwords or password hashes. services/auth.py never passes these to the
logger; if a future change adds logging there, it must log only
`username` / `user_id`, never `password` or `password_hash`.
"""
from __future__ import annotations
import logging
import logging.handlers
import os

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

_configured = False


def _resolve_log_file() -> str:
    """
    Resolve the log file path via database.paths.get_logs_dir(). Imported
    lazily (inside the function, not at module load time) so that
    importing core.logging_config never has a hard import-time dependency
    on the database package — some callers (e.g. a very early startup
    error before the DB layer is touched) may want a logger before
    anything database-related is imported.
    """
    try:
        from database.paths import get_logs_dir
        return os.path.join(get_logs_dir(), "app.log")
    except Exception:
        # Last-resort fallback: current working directory. Only hit if
        # database.paths itself fails to import/resolve, which should not
        # happen in practice (see database/paths.py).
        return os.path.join(os.getcwd(), "turf_hr_pro.log")


def setup_logging(level: int = logging.INFO) -> None:
    """
    Configure the root application logger once per process. Safe to call
    more than once (subsequent calls are no-ops) — callers don't need to
    track whether some other module already initialized logging.

    Adds two handlers:
      - a rotating file handler (5 files x 2MB) under the resolved logs
        directory, so a runaway error loop can't fill the disk.
      - a console handler, useful when running from source / a terminal.
        (The packaged .exe runs with no console attached — see
        launcher.py's build.spec `console=False` — so this handler is a
        harmless no-op there, not a functional requirement.)
    """
    global _configured
    if _configured:
        return

    root = logging.getLogger("turf_hr_pro")
    root.setLevel(level)

    formatter = logging.Formatter(_LOG_FORMAT)

    try:
        log_file = _resolve_log_file()
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError:
        # Disk/permission problem writing logs must never crash the app —
        # fall through to console-only logging.
        pass

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a logger under the shared 'turf_hr_pro' namespace, ensuring
    logging has been configured at least once."""
    setup_logging()
    if not name.startswith("turf_hr_pro"):
        name = f"turf_hr_pro.{name}"
    return logging.getLogger(name)
