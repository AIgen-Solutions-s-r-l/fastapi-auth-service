# app/schemas/resume_utils.py
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def str_to_bool(value: Any) -> bool:
    """
    Convert any value to boolean, handling 'Yes'/'No' strings.

    Args:
        value: Input value to convert to boolean

    Returns:
        bool: Converted boolean value

    Examples:
        >>> str_to_bool('Yes')
        True
        >>> str_to_bool('No')
        False
        >>> str_to_bool(True)
        True
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() == "yes"
    return bool(value)


def process_boolean_section(data: Dict[str, Any], section_name: str) -> None:
    """
    Process all fields in a section to convert string booleans to Python booleans.

    Args:
        data: Dictionary containing the resume data
        section_name: Name of the section to process
    """
    if section_name in data:
        section_data = data[section_name]
        data[section_name] = {
            k: str_to_bool(v) for k, v in section_data.items()
        }


def convert_json_to_resume_dict(json_data: Dict[str, Any], user_id: int) -> Dict[str, Any]:
    """
    Convert JSON data to a dictionary format suitable for Resume model.

    Args:
        json_data: Raw JSON data containing resume information
        user_id: User ID to associate with the resume

    Returns:
        Dict[str, Any]: Processed resume data ready for validation

    Raises:
        ValueError: If there's an error processing the JSON data
    """
    try:
        processed_data = json_data.copy()

        # Process boolean sections
        boolean_sections = [
            'legal_authorization',
            'work_preferences',
        ]

        for section in boolean_sections:
            process_boolean_section(processed_data, section)

        # Process self_identification boolean fields
        if 'self_identification' in processed_data:
            si_data = processed_data['self_identification']
            for field in ['veteran', 'disability']:
                if field in si_data:
                    si_data[field] = str_to_bool(si_data[field])

        processed_data['user_id'] = user_id
        return processed_data

    except Exception as e:
        logger.error(f"Error processing JSON data: {str(e)}", exc_info=True)
        raise ValueError(f"Error processing JSON data: {str(e)}")