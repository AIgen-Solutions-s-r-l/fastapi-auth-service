"""JSON utilities for handling custom types."""

import json
from decimal import Decimal
from typing import Any


class CustomJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles Decimal values."""
    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


def custom_json_dumps(obj: Any) -> str:
    """Dump object to JSON string with custom encoder."""
    return json.dumps(obj, cls=CustomJSONEncoder)