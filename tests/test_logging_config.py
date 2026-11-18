"""Tests for the central logging policy in ``backend.logging_config``.

The policy is what makes ``LOG_LEVEL`` meaningful: DEBUG shows everything, INFO
hides successful HTTP traffic, ERROR shows only errors plus startup messages.
These tests pin that behaviour down without starting the app.
"""
import logging

from backend.logging_config import (
    DEFAULT_LEVEL_NAME,
    STARTUP_FLAG,
    LevelPolicyFilter,
    LoggerNameAliasFilter,
    access_level,
    active_policy_name,
    configure_logging,
    level_name,
    log_startup,
    resolve_level,
    resolve_policy,
)


def test_resolve_policy_accepts_supported_values():
    assert resolve_policy("ALL") == "ALL"
    assert resolve_policy("all") == "ALL"
    assert resolve_policy("DEBUG") == "DEBUG"
    assert resolve_policy(" INFO ") == "INFO"
    assert resolve_policy("ERROR") == "ERROR"


def test_resolve_policy_falls_back_to_info():
    assert resolve_policy("WARNING") == "INFO"
    assert resolve_policy("verbose") == "INFO"
    assert resolve_policy("") == "INFO"
    assert resolve_policy(None) == "INFO"


def test_resolve_level_accepts_supported_values():
    assert resolve_level("ALL") == logging.DEBUG
    assert resolve_level("DEBUG") == logging.DEBUG
    assert resolve_level("debug") == logging.DEBUG
    assert resolve_level(" INFO ") == logging.INFO
    assert resolve_level("ERROR") == logging.ERROR


def test_resolve_level_falls_back_to_info():
    # WARNING is deliberately unsupported: it would hide error context while
    # still printing every recoverable problem.
    assert resolve_level("WARNING") == logging.INFO
    assert resolve_level("verbose") == logging.INFO
    assert resolve_level("") == logging.INFO
    assert resolve_level(None) == logging.INFO
    assert resolve_level(DEFAULT_LEVEL_NAME) == logging.INFO


def test_level_name_round_trip():
    assert level_name(logging.DEBUG) == "DEBUG"
    assert level_name(logging.INFO) == "INFO"
    assert level_name(logging.ERROR) == "ERROR"


def test_access_level_maps_status_codes():
    assert access_level(200) == logging.DEBUG
    assert access_level(204) == logging.DEBUG
    assert access_level(302) == logging.DEBUG
    assert access_level(400) == logging.WARNING
    assert access_level(404) == logging.WARNING
    assert access_level(500) == logging.ERROR
    assert access_level(503) == logging.ERROR


def _record(level: int, startup: bool = False) -> logging.LogRecord:
    record = logging.LogRecord(
        name="test",
        level=level,
        pathname=__file__,
        lineno=1,
        msg="message",
        args=(),
        exc_info=None,
    )
    if startup:
        setattr(record, STARTUP_FLAG, True)
    return record


def test_filter_is_noop_below_error():
    for level in (logging.DEBUG, logging.INFO):
        policy = LevelPolicyFilter(level)
        assert policy.filter(_record(logging.DEBUG))
        assert policy.filter(_record(logging.INFO))
        assert policy.filter(_record(logging.WARNING))
        assert policy.filter(_record(logging.ERROR))


def test_filter_at_error_keeps_only_errors_and_startup():
    policy = LevelPolicyFilter(logging.ERROR)
    assert not policy.filter(_record(logging.DEBUG))
    assert not policy.filter(_record(logging.INFO))
    assert not policy.filter(_record(logging.WARNING))
    assert policy.filter(_record(logging.ERROR))
    assert policy.filter(_record(logging.CRITICAL))
    # Startup messages are the one exception at the strictest level.
    assert policy.filter(_record(logging.INFO, startup=True))


def test_log_startup_marks_record():
    logger = logging.getLogger("test.log_startup")
    captured = []

    class _Capture(logging.Handler):
        def emit(self, record):
            captured.append(record)

    handler = _Capture()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        log_startup(logger, "starting up %s", "now")
    finally:
        logger.removeHandler(handler)

    assert len(captured) == 1
    record = captured[0]
    assert record.levelno == logging.INFO
    assert record.getMessage() == "starting up now"
    assert getattr(record, STARTUP_FLAG) is True


def test_configure_logging_is_idempotent():
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    try:
        configure_logging("DEBUG")
        first = list(root.handlers)
        configure_logging("DEBUG")
        second = list(root.handlers)

        # Reconfiguring must replace the handler, not stack a second one.
        assert len(first) == 1
        assert len(second) == 1
        assert root.level == logging.DEBUG
    finally:
        for handler in list(root.handlers):
            root.removeHandler(handler)
        for handler in original_handlers:
            root.addHandler(handler)
        root.setLevel(original_level)


def test_configure_logging_error_keeps_root_at_info():
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    try:
        configure_logging("ERROR")
        # The root logger must stay at INFO so startup records reach the filter.
        assert root.level == logging.INFO
        handler = root.handlers[0]
        assert any(isinstance(f, LevelPolicyFilter) for f in handler.filters)
    finally:
        for handler in list(root.handlers):
            root.removeHandler(handler)
        for handler in original_handlers:
            root.addHandler(handler)
        root.setLevel(original_level)


def test_configure_logging_silences_uvicorn_access():
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    access = logging.getLogger("uvicorn.access")
    original_disabled = access.disabled
    try:
        configure_logging("INFO")
        assert access.disabled is True
        assert access.propagate is False
    finally:
        access.disabled = original_disabled
        for handler in list(root.handlers):
            root.removeHandler(handler)
        for handler in original_handlers:
            root.addHandler(handler)
        root.setLevel(original_level)


def test_database_loggers_only_enabled_at_all():
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    db_loggers = [logging.getLogger(name) for name in ("aiosqlite", "sqlite3")]
    original_db_levels = [logger.level for logger in db_loggers]
    try:
        configure_logging("DEBUG")
        # DEBUG must not drown the app's own output in per-query noise.
        assert all(logger.level == logging.WARNING for logger in db_loggers)

        configure_logging("ALL")
        assert all(logger.level == logging.DEBUG for logger in db_loggers)
        assert active_policy_name() == "ALL"
    finally:
        for logger, level in zip(db_loggers, original_db_levels):
            logger.setLevel(level)
        for handler in list(root.handlers):
            root.removeHandler(handler)
        for handler in original_handlers:
            root.addHandler(handler)
        root.setLevel(original_level)


def test_logger_name_alias_renames_uvicorn_error():
    alias = LoggerNameAliasFilter()
    record = logging.LogRecord(
        name="uvicorn.error",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Application startup complete.",
        args=(),
        exc_info=None,
    )
    assert alias.filter(record) is True
    assert record.name == "uvicorn"


def test_logger_name_alias_leaves_other_loggers_alone():
    alias = LoggerNameAliasFilter()
    record = logging.LogRecord(
        name="backend.main",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    assert alias.filter(record) is True
    assert record.name == "backend.main"


if __name__ == "__main__":
    for name, func in sorted(globals().items()):
        if name.startswith("test_") and callable(func):
            func()
            print(f"PASS {name}")
