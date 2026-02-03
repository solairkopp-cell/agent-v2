class FailureReason:
    def __init__(self, failure_reason_code, label,is_active):
        self.failure_reason_code = failure_reason_code
        self.label = label
        self.is_active = is_active
    def __str__(self):
        return f"FailureReason(code={self.failure_reason_code}, label={self.label}, is_active={self.is_active})"