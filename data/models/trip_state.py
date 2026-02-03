from enum import Enum

class TripState(Enum):
    """Represents the different states of a trip"""
    NOT_STARTED = "notStarted"
    IN_PROGRESS = "inProgress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    
    @classmethod
    def from_string(cls, value: str) -> 'TripState':
        """Convertit une string en TripState"""
        for state in cls:
            if state.value == value:
                return state
        raise ValueError(f"Invalid trip state: {value}")