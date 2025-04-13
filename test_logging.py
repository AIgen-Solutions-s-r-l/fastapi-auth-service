import sys
from app.log.logging import loguru_logger, logconfig

# Remove existing handlers
loguru_logger.remove()

# Add a new handler with DEBUG level
loguru_logger.add(sys.stdout, format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS Z}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <level>{message}</level> | <level>{extra}</level>",
    level="DEBUG")

# Test logging with extra parameters at DEBUG level
loguru_logger.debug("Test DEBUG message with extra parameters",
                   event_type="test_debug_event",
                   test_id="456",
                   test_name="debug_logging_test",
                   test_status="running")

# Test logging with extra parameters at INFO level
loguru_logger.info("Test INFO message with extra parameters",
                  event_type="test_info_event",
                  test_id="123",
                  test_name="info_logging_test",
                  test_status="running")

print("Logging test completed. Check the console output above to verify that extra parameters are displayed.")