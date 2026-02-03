class Stop:
    def __init__(self , ID_stop,ID_planning,ID_address,sequence_index,status,planned_arrival_at,eta_arrival_at,actual_arrival,actual_departure_at,notes):
        self.ID_stop = ID_stop
        self.ID_planning = ID_planning
        self.ID_address = ID_address
        self.sequence_index = sequence_index
        self.status = status
        self.planned_arrival_at = planned_arrival_at
        self.eta_arrival_at = eta_arrival_at
        self.actual_arrival = actual_arrival
        self.actual_departure_at = actual_departure_at
        self.notes = notes
        def __str__(self):
            return f"Stop(ID_stop={self.ID_stop}, ID_planning={self.ID_planning}, ID_address={self.ID_address}, sequence_index={self.sequence_index}, status={self.status}, planned_arrival_at={self.planned_arrival_at}, eta_arrival_at={self.eta_arrival_at}, actual_arrival={self.actual_arrival}, actual_departure_at={self.actual_departure_at}, notes={self.notes})"