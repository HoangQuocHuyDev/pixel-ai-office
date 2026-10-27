import logging
import re


LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
HANDLER_MARKER = "_pixel_ai_office_handler"
SENSITIVE_VALUE_PATTERN = re.compile(
    r"(?i)\b(password|token|secret|database_url|gemini_api_key|api[_-]?key|authorization)(\s*[:=]\s*)([^\s,;]+)"
)


class SensitiveDataFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        formatted_message = super().format(record)
        return SENSITIVE_VALUE_PATTERN.sub(r"\1\2[REDACTED]", formatted_message)


def configure_logging(log_level: str) -> None:
    root_logger = logging.getLogger()
    level = getattr(logging, log_level.upper(), logging.INFO)
    root_logger.setLevel(level)

    formatter = SensitiveDataFormatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    application_handlers = [
        handler
        for handler in root_logger.handlers
        if getattr(handler, HANDLER_MARKER, False)
    ]

    if application_handlers:
        handler = application_handlers[0]
    else:
        handler = logging.StreamHandler()
        setattr(handler, HANDLER_MARKER, True)
        root_logger.addHandler(handler)

    handler.setLevel(level)
    handler.setFormatter(formatter)
