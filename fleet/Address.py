class Address:
    def __init__(self,id_address, line1,postal_code,city,country_code,lat,lon,place_id,instructions):
        self.id_address = id_address
        self.street = line1
        self.zip_code = postal_code
        self.city = city
        self.state = country_code
        self.latitude = lat
        self.longitude = lon
        self.place_id = place_id
        self.instructions = instructions
        

    def __str__(self):
        return (f"Address {self.id_address}: {self.street}, {self.city}, {self.state} {self.zip_code} | "
                f"Lat: {self.latitude}, Lon: {self.longitude} | Instructions: {self.instructions}")