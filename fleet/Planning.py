class Planning :
    def __init__(self, ID_planning,ID_Driver,Date,start_at,end_at,Status,ID_vehicule,created_at,updated_at):
        self.ID_planning = ID_planning
        self.ID_Driver = ID_Driver
        self.Date = Date
        self.start_at = start_at
        self.end_at = end_at
        self.Status = Status
        self.ID_vehicule = ID_vehicule
        self.created_at = created_at
        self.updated_at = updated_at
    def __str__(self):
        return f"Planning(ID_planning={self.ID_planning}, ID_Driver={self.ID_Driver}, Date={self.Date}, start_at={self.start_at}, end_at={self.end_at}, Status={self.Status}, ID_vehicule={self.ID_vehicule}, created_at={self.created_at}, updated_at={self.updated_at})"