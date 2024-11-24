import sys
import socket
import json
from datetime import datetime
from loguru import logger


class TcpSink:
    """TCP Sink for sending logs to Logstash with ECS compatibility"""

    def __init__(self, host: str, port: int, app_name: str):
        self.host = host
        self.port = port
        self.app_name = app_name

    def __call__(self, message):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((self.host, self.port))

            record = message.record

            # Create ECS-compatible log data
            log_data = {
                "@timestamp": record["time"].strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                "message": record["message"],
                "log": {
                    "level": record["level"].name.lower(),
                    "logger": record["module"],
                    "origin": {
                        "function": record["function"],
                        "file": {
                            "line": record["line"],
                            "name": record["file"].name
                        }
                    }
                },
                "service": {
                    "name": self.app_name,
                    "type": "auth-service"
                },
                "event": {
                    "kind": "event",
                    "category": "authentication",
                    "type": "info",
                    "created": record["time"].strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
                },
                "process": {
                    "pid": record["process"].id,
                    "thread": {
                        "id": record["thread"].id
                    }
                },
                "type": "syslog-modern"
            }

            # Add extra fields in a structured way
            if record["extra"]:
                custom_fields = {}
                for k, v in record["extra"].items():
                    custom_fields[k] = v
                if custom_fields:
                    log_data["labels"] = custom_fields

            # Add exception info if present
            if record["exception"] is not None:
                log_data["error"] = {
                    "message": str(record["exception"]),
                    "type": record["exception"].__class__.__name__
                }

            # Send the JSON data
            sock.sendall(json.dumps(log_data).encode() + b'\n')
            sock.close()
        except Exception as e:
            print(f"Error sending log to Logstash: {e}", file=sys.stderr)


class LogConfig:
    """Logging configuration for the application"""

    @staticmethod
    def setup_logging(
            app_name: str = "auth-service",
            log_level: str = "DEBUG",
            syslog_host: str = "localhost",
            syslog_port: int = 5141,
            json_logs: bool = True
    ) -> None:
        """Configure loguru logger"""
        # Remove default handler
        logger.remove()

        # Console handler with nice formatting
        logger.add(
            sys.stdout,
            format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            level=log_level,
            colorize=True
        )

        # TCP handler for Logstash
        tcp_sink = TcpSink(
            host=syslog_host,
            port=syslog_port,
            app_name=app_name
        )

        logger.add(
            tcp_sink,
            level=log_level,
            serialize=True,
            enqueue=True,
            backtrace=True,
            diagnose=True,
            catch=True
        )

    @staticmethod
    def get_logger():
        """Returns the configured logger instance"""
        return logger


def test_connection(host="localhost", port=5141) -> bool:
    """Test connection to Logstash"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        test_msg = {
            "@timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "message": "Connection test",
            "log": {
                "level": "info"
            },
            "service": {
                "name": "connection-test"
            },
            "type": "syslog-modern"
        }
        sock.send(json.dumps(test_msg).encode() + b'\n')
        sock.close()
        print("Logstash connection test successful")
        return True
    except Exception as e:
        print(f"Logstash connection test failed: {e}")
        return False


def init_logging(settings) -> logger:
    """Initialize logging with settings"""
    try:
        LogConfig.setup_logging(
            app_name=settings.service_name,
            log_level=settings.log_level,
            syslog_host=settings.syslog_host,
            syslog_port=settings.syslog_port,
            json_logs=settings.json_logs
        )
        return logger
    except Exception as e:
        print(f"Failed to initialize logging: {e}")
        # Fallback to basic console logging
        logger.remove()
        logger.add(sys.stdout, format="{time} | {level} | {message}")
        return logger


__all__ = ['init_logging', 'test_connection', 'logger']