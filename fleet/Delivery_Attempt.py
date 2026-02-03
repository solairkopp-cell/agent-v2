class Delivery_Attempt:
    def __init__(self, id_attempt, ID_delivery,ID_stop,attempted_at, status,failure_reason_code,comment,client_at_home,warning,gps,photo,signature):
        self.id_attempt = id_attempt
        self.ID_delivery = ID_delivery
        self.ID_stop = ID_stop
        self.attempted_at = attempted_at
        self.status = status
        self.failure_reason_code = failure_reason_code
        self.comment = comment
        self.client_at_home = client_at_home
        self.warning = warning
        self.gps = gps
        self.photo = photo
        self.signature = signature
    def __str__(self):
        return f"Delivery_Attempt(id_attempt={self.id_attempt}, ID_delivery={self.ID_delivery}, ID_stop={self.ID_stop}, attempted_at={self.attempted_at}, status={self.status}, failure_reason_code={self.failure_reason_code}, comment={self.comment}, client_at_home={self.client_at_home}, warning={self.warning}, gps={self.gps}, photo={self.photo}, signature={self.signature})"