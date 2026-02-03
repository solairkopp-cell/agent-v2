class Driver:
    def __init__(self, name, Email, Phone_Number,ID_driver,is_active,created_at,updated_at):
        self.name = name
        self.Email = Email
        self.Phone_Number = Phone_Number
        self.ID_driver = ID_driver
        self.is_active = is_active
        self.created_at = created_at
        self.updated_at = updated_at
    
    def __str__(self):
        return (f"Driver {self.driver_id}: {self.name}, Email: {self.email}, "
                f"Phone: {self.phone_number}, Active: {self.is_active}")