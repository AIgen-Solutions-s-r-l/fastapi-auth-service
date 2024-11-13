# app/schemas/resume_utils.py
import logging

logger = logging.getLogger(__name__)


def str_to_bool(value) -> bool:
    """Convert any value to boolean, handling 'Yes'/'No' strings"""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() == "yes"
    return bool(value)


def convert_yaml_to_resume_dict(yaml_data: dict, user_id: int) -> dict:
    """Convert YAML data to a dictionary format suitable for Resume model."""
    try:
        processed_data = yaml_data.copy()

        # Process legal_authorization booleans
        if 'legal_authorization' in processed_data:
            auth_data = processed_data['legal_authorization']
            processed_data['legal_authorization'] = {
                k: str_to_bool(v) for k, v in auth_data.items()
            }

        # Process work_preferences booleans
        if 'work_preferences' in processed_data:
            pref_data = processed_data['work_preferences']
            processed_data['work_preferences'] = {
                k: str_to_bool(v) for k, v in pref_data.items()
            }

        # Process self_identification booleans
        if 'self_identification' in processed_data:
            si_data = processed_data['self_identification']
            if 'veteran' in si_data:
                si_data['veteran'] = str_to_bool(si_data['veteran'])
            if 'disability' in si_data:
                si_data['disability'] = str_to_bool(si_data['disability'])

        processed_data['user_id'] = user_id
        return processed_data

    except Exception as e:
        logger.error(f"Error processing YAML data: {str(e)}")
        raise ValueError(f"Error processing YAML data: {str(e)}")