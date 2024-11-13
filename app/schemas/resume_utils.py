# app/schemas/resume_utils.py
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def str_to_bool(value: Any) -> bool:
    """Convert any value to boolean, handling 'Yes'/'No' strings"""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() == "yes"
    return bool(value)


def process_boolean_fields(data: Dict[str, Any], fields: List[str]) -> Dict[str, Any]:
    """
    Process boolean fields in a dictionary.

    Args:
        data: Dictionary containing fields to process
        fields: List of field names to convert to boolean

    Returns:
        Dictionary with processed boolean fields
    """
    processed = data.copy()
    for field in fields:
        if field in processed:
            processed[field] = str_to_bool(processed[field])
    return processed


def convert_yaml_to_resume_dict(yaml_data: Dict[str, Any], user_id: int) -> Dict[str, Any]:
    """
    Convert YAML data to a dictionary format suitable for Resume model.

    Args:
        yaml_data: The parsed YAML data
        user_id: The user ID to include in the resume

    Returns:
        Dictionary containing the structured resume data

    Raises:
        ValueError: If YAML data is invalid
    """
    try:
        # Define boolean fields for each section
        work_auth_fields = [
            'eu_work_authorization', 'us_work_authorization', 'requires_us_visa',
            'requires_us_sponsorship', 'requires_eu_visa', 'legally_allowed_to_work_in_eu',
            'legally_allowed_to_work_in_us', 'requires_eu_sponsorship',
            'canada_work_authorization', 'requires_canada_visa',
            'legally_allowed_to_work_in_canada', 'requires_canada_sponsorship',
            'uk_work_authorization', 'requires_uk_visa', 'legally_allowed_to_work_in_uk',
            'requires_uk_sponsorship'
        ]
        work_pref_fields = [
            'remote_work', 'in_person_work', 'open_to_relocation',
            'willing_to_complete_assessments', 'willing_to_undergo_drug_tests',
            'willing_to_undergo_background_checks'
        ]
        self_id_fields = ['veteran', 'disability']

        # Process boolean fields
        processed_data = yaml_data.copy()
        processed_data['legal_authorization'] = process_boolean_fields(
            yaml_data['legal_authorization'], work_auth_fields)
        processed_data['work_preferences'] = process_boolean_fields(
            yaml_data['work_preferences'], work_pref_fields)
        processed_data['self_identification'] = process_boolean_fields(
            yaml_data['self_identification'], self_id_fields)

        # Add user_id
        processed_data['user_id'] = user_id

        return processed_data

    except KeyError as e:
        error_msg = f"Missing required field in YAML data: {str(e)}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    except Exception as e:
        error_msg = f"Error processing YAML data: {str(e)}"
        logger.error(error_msg)
        raise ValueError(error_msg)
