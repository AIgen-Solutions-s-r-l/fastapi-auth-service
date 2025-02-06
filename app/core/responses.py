"""Custom response classes for the application."""

from typing import Any
from fastapi.responses import JSONResponse
from app.core.json_utils import custom_json_dumps


class DecimalJSONResponse(JSONResponse):
    """JSONResponse that properly handles Decimal values."""
    def render(self, content: Any) -> bytes:
        """Override render to use custom JSON encoder."""
        return custom_json_dumps(content).encode('utf-8')