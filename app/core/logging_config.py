import sys
import socket
from typing import Dict, Any
from loguru import logger


class LogConfig:
    """
    Logging configuration for the application using loguru.
    Handles both console output and syslog forwarding for ELK stack.
    """

    @staticmethod
    def setup_logging(
            app_name: str = "auth-service",
            log_level: str = "DEBUG",
            syslog_host: str = "localhost",
            syslog_port: int = 514,
            json_logs: bool = True
    ) -> None:
        """
        Configure loguru logger with console and syslog handlers
        """
        # Remove default handler
        logger.remove()

        # Define a function to inject extra fields
        def formatter(record):
            record["extra"].update({
                "app_name": app_name,
                "hostname": socket.gethostname()
            })

            if json_logs:
                # JSON format for syslog/ELK
                return {
                    "timestamp": record["time"].strftime("%Y-%m-%d %H:%M:%S.%f"),
                    "level": record["level"].name,
                    "message": record["message"],
                    "module": record["module"],
                    "function": record["function"],
                    "line": record["line"],
                    "app_name": record["extra"]["app_name"],
                    "hostname": record["extra"]["hostname"]
                }
            else:
                # Human readable format for console
                return "{time} | {level} | {message}\n"

        # Add console handler
        logger.add(
            sys.stdout,
            format=formatter if not json_logs else "{message}",
            level=log_level,
            serialize=False,
            backtrace=True,
            diagnose=True,
        )

        # Add syslog handler
        try:
            logger.add(
                f"socket://{syslog_host}:{syslog_port}",
                format=formatter if json_logs else "{message}",
                level=log_level,
                serialize=json_logs,
                backtrace=True,
                diagnose=True,
                enqueue=True,
            )
        except Exception as e:
            logger.error(f"Failed to configure syslog handler: {str(e)}")

    @staticmethod
    def get_logger():
        """Returns the configured logger instance"""
        return logger


# Initialize a default logger instance
default_logger = LogConfig.get_logger()