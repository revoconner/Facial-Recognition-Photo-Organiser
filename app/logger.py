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
    global _configured, _gui_handler

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

        # In-app log viewer handler. Same format as file/console so the GUI log
        # mirrors them exactly. It buffers from here (process start) so lines logged
        # before the window exists are not lost; the API hands the backlog to the UI
        # once the front end is ready (see activate_gui_log / api.get_log_history).
        _gui_handler = GuiLogHandler()
        _gui_handler.setFormatter(fmt)
        logger.addHandler(_gui_handler)

        # Don't also propagate to the root logger (would double-log).
        logger.propagate = False
        _configured = True

    return logger


def set_level(level_name):
    """Change the active log level at runtime (e.g. from a settings toggle)."""
    logging.getLogger(_LOGGER_NAME).setLevel(_resolve_level(level_name))


class GuiLogHandler(logging.Handler):
    """Buffers formatted log lines from process start, then forwards them live to the
    in-app log viewer once a callback is supplied (api._push_log_to_gui). This lets the
    GUI mirror the console - including everything logged before the window existed - and
    is essential in the packaged build, which has no console at all.

    Exceptions are swallowed so logging never breaks the app, and the callback must NOT
    log through this logger or it would recurse. The logger's level governs what reaches
    here (Normal -> INFO and up, Debug -> everything)."""

    def __init__(self, max_buffer=5000):
        super().__init__()
        self._buffer = []
        self._max_buffer = max_buffer
        self._callback = None

    def activate_and_snapshot(self, callback):
        """Switch to live forwarding and return everything buffered so far, atomically
        so the handover neither drops nor duplicates a line. Returns a list of lines."""
        self.acquire()
        try:
            self._callback = callback
            return list(self._buffer)
        finally:
            self.release()

    def emit(self, record):
        try:
            line = self.format(record)
        except Exception:
            return
        self.acquire()
        try:
            self._buffer.append(line)
            if len(self._buffer) > self._max_buffer:
                del self._buffer[:-self._max_buffer]
            callback = self._callback
        finally:
            self.release()
        if callback is not None:
            try:
                callback(line)
            except Exception:
                pass


_gui_handler = None


def activate_gui_log(emit_callback):
    """Begin mirroring logs to the GUI and return the backlog (lines logged before the
    GUI was ready) so the front end can render them. emit_callback(text) pushes one line
    to the UI. Returns [] if logging hasn't been set up yet."""
    if _gui_handler is None:
        return []
    return _gui_handler.activate_and_snapshot(emit_callback)


def get_logger(name=None):
    """Return the app logger, or a named child of it (e.g. get_logger('api'))."""
    base = logging.getLogger(_LOGGER_NAME)
    return base.getChild(name) if name else base
