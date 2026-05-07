import logging
from contextvars import ContextVar
from typing import Any

correlation_id_ctx: ContextVar[str | None] = ContextVar("correlation_id", default=None)


class JsonSafeFormatter(logging.Formatter):
    """Emit JSON lines for structured logs (sanitized)."""

    def format(self, record: logging.LogRecord) -> str:
        import json
        from datetime import UTC, datetime

        cid = correlation_id_ctx.get()
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": _sanitize(str(record.getMessage())),
        }
        if cid:
            payload["correlation_id"] = cid
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _sanitize(s: str, max_len: int = 8000) -> str:
    """Strip CR/LF and cap length to reduce log injection."""
    out = s.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    if len(out) > max_len:
        out = out[:max_len] + "…"
    return out


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonSafeFormatter())
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
