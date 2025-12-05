import sys
import os
from logging import StreamHandler
from datadog_api_client.v2 import ApiClient, Configuration
from datadog_api_client.v2.api.logs_api import LogsApi
from datadog_api_client.v2.model.content_encoding import ContentEncoding
from datadog_api_client.v2.model.http_log import HTTPLog
from datadog_api_client.v2.model.http_log_item import HTTPLogItem
from loguru import logger as loguru_logger
import logging
import inspect


def get_request_id_for_logging() -> str:
    """
    Get the current request ID for logging purposes.

    This function safely imports and retrieves the request ID from the middleware,
    avoiding circular imports.

    Returns:
        The current request ID or "no-request-id" if not in a request context.
    """
    try:
        from app.middleware.request_id import get_request_id
        request_id = get_request_id()
        return request_id if request_id else "no-request-id"
    except ImportError:
        return "no-request-id"

class LogConfig:
    def __init__(self):
        self.enviroment = os.getenv('ENVIRONMENT', 'development')
        self.service = os.getenv('SERVICE_NAME', 'default_service_name')
        self.hostname = os.getenv('HOSTNAME', 'unknown')
        self.loglevel = os.getenv('LOGLEVEL', 'INFO')
        self.loglevel_dd = os.getenv('LOGLEVEL_DATADOG', 'ERROR')

# Istanza globale della configurazione
logconfig = LogConfig()

class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        # Get corresponding Loguru level if it exists.
        try:
            level: str | int = loguru_logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message.
        frame, depth = inspect.currentframe(), 0
        while frame:
            filename = frame.f_code.co_filename
            is_logging = filename == logging.__file__
            is_frozen = "importlib" in filename and "_bootstrap" in filename
            if depth > 0 and not (is_logging or is_frozen):
                break
            frame = frame.f_back
            depth += 1

        # Extract extra attributes from the record
        extra = {}
        for key, value in record.__dict__.items():
            if key not in {
                'args', 'asctime', 'created', 'exc_info', 'exc_text', 'filename',
                'funcName', 'id', 'levelname', 'levelno', 'lineno', 'module',
                'msecs', 'message', 'msg', 'name', 'pathname', 'process',
                'processName', 'relativeCreated', 'stack_info', 'thread', 'threadName'
            }:
                extra[key] = value

        # Pass the extra parameters to Loguru
        logger = loguru_logger.opt(depth=depth, exception=record.exc_info)
        logger.bind(**extra).log(level, record.getMessage())

class DatadogHandler(StreamHandler):
    def __init__(self):
        super().__init__()
        configuration = Configuration()
        self.api_client = ApiClient(configuration)
        self.api_instance = LogsApi(self.api_client)

    def emit(self, record):
        log_message = self.format(record)
        log_level = record.levelname

        if record.extra:
            for key, value in record.extra.items():
                try:
                    record.extra[key] = str(value)
                except Exception:
                    record.extra.pop(key)

        # Get request_id from extra or context
        request_id = record.extra.get("request_id", get_request_id_for_logging())

        log = {
            "status": log_level,
            "ddsource": "loguru",
            "ddtags": f"level:{log_level},env:{logconfig.enviroment}",
            "message": log_message,
            "service": logconfig.service,
            "timestamp": str(record.created),
            "hostname": logconfig.hostname,
            "request_id": request_id,
            **record.extra,
        }

        http_log_item = HTTPLogItem(
            **log
        )

        http_log = HTTPLog([http_log_item])

        self.api_instance.submit_log(content_encoding=ContentEncoding.DEFLATE, body=http_log)


def request_id_patcher(record):
    """Loguru patcher to add request_id to each log record."""
    record["extra"]["request_id"] = get_request_id_for_logging()


def init_logging():
    try:
        # Configura il logger di loguru
        loguru_logger.remove()  # Rimuove il logger predefinito di loguru

        # Configure logger with request ID patcher
        loguru_logger.configure(patcher=request_id_patcher)

        # Aggiungi un handler per la console with request_id in format
        loguru_logger.add(
            sys.stdout,
            format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS Z}</green> | "
                   "<level>{level: <8}</level> | "
                   "<blue>[{extra[request_id]}]</blue> | "
                   "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                   "<level>{message}</level> | <level>{extra}</level>",
            level=logconfig.loglevel
        )
        
        dd_api_key = os.getenv("DD_API_KEY")

        if dd_api_key and isinstance(dd_api_key, str) and len(dd_api_key) > 1:
            # Aggiungi un handler per datadog
            loguru_logger.add(DatadogHandler(), level=logconfig.loglevel_dd)
        else:
            loguru_logger.warning("Datadog API key is not set or environment variable is invalid. Logging to console only.")
        
        
        return loguru_logger
    except Exception as e:
        print(f"Failed to initialize logging: {e}")
        # Fallback to basic console logging
        loguru_logger.remove()
        loguru_logger.add(sys.stdout, format="{time} | {level} | {message}", level="DEBUG")
        return loguru_logger
    
logger = init_logging()