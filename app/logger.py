"""Application logging for Felicity.

Provides a single configured logger ("felicity") that writes to a rotating file in
the app-data folder and to stdout. Used so that scan/cluster/UI events end up in a
persistent, timestamped, level-controlled log that users can attach to bug reports,
rather than scattered print() calls that vanish with the console.

Levels exposed to the user (mapped to Python logging levels):
    OFF      - logging disabled
    ERROR    - errors only
    INFO     - normal operational messages (default)
    VERBOSE  - extra detail, between INFO and DEBUG
    DEBUG    - everything, for development

The verbosity control UI lives under Advanced > Developer (see PLAN-todo.md F5); for
now the level is read from the 'log_level' setting.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Custom level sitting between DEBUG (10) and INFO (20) so "verbose" is distinct
# from full "debug" output.
VERBOSE = 15
logging.addLevelName(VERBOSE, "VERBOSE")

# User-facing level name -> logging level. OFF is set above CRITICAL so nothing
# is emitted.
LEVELS = {
    "OFF": logging.CRITICAL + 10,
    "ERROR": logging.ERROR,
    "INFO": logging.INFO,
    "VERBOSE": VERBOSE,
    "DEBUG": logging.DEBUG,
}

_LOGGER_NAME = "felicity"
_configured = False


def _verbose(self, message, *args, **kwargs):
    """logger.verbose(...) - log at the custom VERBOSE level."""
    if self.isEnabledFor(VERBOSE):
        self._log(VERBOSE, message, args, **kwargs)


# Attach .verbose() to every logger instance once, at import time.
logging.Logger.verbose = _verbose


def _resolve_level(level_name):
    return LEVELS.get((level_name or "INFO").upper(), logging.INFO)


def setup_logging(log_dir, level_name="INFO"):
    """Configure the 'felicity' logger and return it.

    Attaches a rotating file handler (in log_dir) plus a stdout handler on the first
    call; later calls only adjust the level, so it is safe to call more than once.

    The file handler uses UTF-8 with backslashreplace error handling so that paths
    containing characters outside the system code page (e.g. 'U+018F') never raise a
    UnicodeEncodeError while logging.
    """
    global _configured

    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(_resolve_level(level_name))

    if not _configured:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "felicity.log"

        fmt = logging.Formatter(
            "%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # Rotate at ~2 MB, keep 5 old files, so the log can't grow unbounded.
        file_handler = RotatingFileHandler(
            str(log_path),
            maxBytes=2_000_000,
            backupCount=5,
            encoding="utf-8",
            errors="backslashreplace",
        )
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)

        # Keep console output during development.
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(fmt)
        logger.addHandler(stream_handler)

        # Don't also propagate to the root logger (would double-log).
        logger.propagate = False
        _configured = True

    return logger


def set_level(level_name):
    """Change the active log level at runtime (e.g. from a settings toggle)."""
    logging.getLogger(_LOGGER_NAME).setLevel(_resolve_level(level_name))


def get_logger(name=None):
    """Return the app logger, or a named child of it (e.g. get_logger('api'))."""
    base = logging.getLogger(_LOGGER_NAME)
    return base.getChild(name) if name else base
