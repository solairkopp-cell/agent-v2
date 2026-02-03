class Delivery:
    def __init__(self,ID_delivery,name,additionalInfo,packageInfo,status,created_at,updated_at):
        self.ID_delivery = ID_delivery
        self.name = name
        self.additionalInfo = additionalInfo
        self.packageInfo = packageInfo
        self.status = status
        self.created_at = created_at
        self.updated_at = updated_at
    def __str__(self):
        return (f"Delivery {self.ID_delivery}: {self.name}, Status: {self.status}, "
                f"Package Info: {self.package_info}, Additional Info: {self.additional_info}, "
                f"Created At: {self.created_at}, Updated At: {self.updated_at}") 