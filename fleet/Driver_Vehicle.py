class Driver_Vehicule:
    def __init__(self, ID_driver, id_vehicle,start_date,end_date):
        self.ID_driver = ID_driver
        self.id_vehicle = id_vehicle
        self.start_date = start_date
        self.end_date = end_date
    def __str__(self):
        return f"Driver_Vehicule(driver_id={self.ID_driver}, id_vehicule={self.id_vehicle}, start_date={self.start_date}, end_date={self.end_date})"