"""
Domain Models - Delivery Context and Business Rules
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class DeliveryState(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    COMPLETED_WITH_PHOTO = "completed_with_photo"
    FAILED = "failed"



class FailureReason(Enum):
    """Predefined failure reasons"""
    RECIPIENT_ABSENT = "1"
    NO_SAFE_PLACE = "2"
    ACCESS_DENIED = "3"
    ADDRESS_INCORRECT = "4"
    RECIPIENT_REFUSED = "5"
    OTHER = "6"
    
    @classmethod
    def from_number(cls, number: str) -> Optional['FailureReason']:
        """Get reason from number string"""
        for reason in cls:
            if reason.value == number:
                return reason
        return None
    
    def get_text(self) -> str:
        """Get human-readable text"""
        mapping = {
            "1": "the recipient was absent",
            "2": "no safe place to leave the package",
            "3": "access not possible (closed door, intercom, secured building)",
            "4": "address not found or incorrect",
            "5": "the recipient refused the delivery",
            "6": "another reason"
        }
        return mapping.get(self.value, "unknown reason")


@dataclass
class DeliveryContext:
    """Rich context for a delivery in progress"""
    delivery_id: str
    state: DeliveryState = DeliveryState.PENDING
    failure_reason: Optional[FailureReason] = None
    failure_reason_text: Optional[str] = None  # For custom reason (option 6)
    photo_taken: bool = False
    completed_at: Optional[datetime] = None
    address: str = ""
    client_name: str = ""
    
    def get_failure_description(self) -> str:
        """Get complete failure description"""
        if self.failure_reason_text:
            return self.failure_reason_text
        if self.failure_reason:
            return self.failure_reason.get_text()
        return "unknown"


class DeliveryRules:
    """Business rules for delivery completion"""
    
    @staticmethod
    def can_complete_without_photo(ctx: DeliveryContext) -> bool:
        """Can complete delivery without photo (client present case)"""
        return ctx.failure_reason is None
    
    @staticmethod
    def requires_photo(reason: Optional[FailureReason]) -> bool:
        """
        Does this failure reason require a photo?
        BUSINESS RULE: Only RECIPIENT_ABSENT requires photo proof.
        """
        return reason == FailureReason.RECIPIENT_ABSENT
    
    @staticmethod
    def requires_reason_detail(reason: Optional[FailureReason]) -> bool:
        """Does this reason need custom text detail?"""
        return reason == FailureReason.OTHER
