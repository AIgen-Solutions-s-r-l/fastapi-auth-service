from enum import Enum
from typing import Optional

from pydantic import BaseModel

class TrialEligibilityReasonCode(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    TRIAL_CONSUMED = "TRIAL_CONSUMED"
    CURRENTLY_IN_TRIAL = "CURRENTLY_IN_TRIAL"
    PREVIOUS_PURCHASE = "PREVIOUS_PURCHASE"
    PAYMENT_HISTORY = "PAYMENT_HISTORY"

class TrialEligibilityResponse(BaseModel):
    is_eligible: bool
    reason_code: TrialEligibilityReasonCode
    message: Optional[str] = None

    class Config:
        use_enum_values = True # Ensures enum values are used in serialization