from enum import Enum, auto


class Event(Enum):
    ARRIVAL = auto()
    CONFIRM_YES = auto()
    CONFIRM_NO = auto()
    REASON_NUMBER = auto()
    REASON_TEXT = auto()
    REASON_PROVIDED = auto()
    PHOTO_TAKEN = auto()
    PHOTO_NOT_TAKEN = auto()
    PHOTO_FAILED = auto()
    CANCEL = auto()
    TIMEOUT = auto()


class DeliveryState(Enum):
    IN_PROGRESS = auto()
    ARRIVED_AT_DESTINATION = auto()
    AWAITING_CONFIRMATION = auto()
    COMPLETED = auto()
    FAILED = auto()


class FailureReason(Enum):
    CLIENT_NOT_AT_HOME = auto()
    NO_SAFE_PLACE = auto()
    REFUSED = auto()
    OTHER = auto()


class AgentMode(Enum):
    NORMAL = auto()
    DELIVERY_TREATMENT = auto()


class TreatmentState(Enum):
    ASK_DELIVERY_COMPLETION = auto()
    ASK_NON_DELIVERY_REASON = auto()
    ASK_REASON_DETAIL = auto()
    ASK_PHOTO = auto()
    WAIT_PHOTO_RESULT = auto()
    FINALIZE = auto()
