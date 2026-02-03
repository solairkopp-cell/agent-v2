class Vehicle:
    def __init__(self,id_vehicle,license_plate,brand, model,type, capacity_kg,capacity_volume,status):
        self.id_vehicle = id_vehicle
        self.model = model
        self.license_plate = license_plate
        self.brand = brand
        self.type = type
        self.capacity_kg = capacity_kg
        self.capacity_volume = capacity_volume
        self.status = status
    def __str__(self):
        return f"Vehicle {self.id_vehicle}: {self.brand} {self.model}, Type: {self.type}, Capacity: {self.capacity_kg}kg / {self.capacity_volume}m³, Status: {self.status}"