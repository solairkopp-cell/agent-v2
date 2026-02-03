from dataclasses import dataclass
from typing import Optional

@dataclass
class Destination:
    """Modèle de destination compatible avec Flutter DestinationModel"""
    id: str
    name: str
    latitude: float
    longitude: float
    additional_info: Optional[str] = None
    is_completed: bool = False
    client_name: Optional[str] = None
    package_info: Optional[str] = None
    client_at_home: bool = False
    warning: bool = False
    
    @property
    def position(self) -> tuple[float, float]:
        """Retourne (latitude, longitude)"""
        return (self.latitude, self.longitude)
    
    def copy_with(self, **kwargs) -> 'Destination':
        """Équivalent de copyWith() de Dart"""
        return Destination(
            id=kwargs.get('id', self.id),
            name=kwargs.get('name', self.name),
            latitude=kwargs.get('latitude', self.latitude),
            longitude=kwargs.get('longitude', self.longitude),
            additional_info=kwargs.get('additional_info', self.additional_info),
            is_completed=kwargs.get('is_completed', self.is_completed),
            client_name=kwargs.get('client_name', self.client_name),
            package_info=kwargs.get('package_info', self.package_info),
            client_at_home=kwargs.get('client_at_home', self.client_at_home),
            warning=kwargs.get('warning', self.warning),
        )
    
    def to_json(self) -> dict:
        """Convertir en dict pour JSON (format Flutter)"""
        return {
            'id': self.id,
            'name': self.name,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'additionalInfo': self.additional_info,
            'isCompleted': self.is_completed,
            'clientName': self.client_name,
            'packageInfo': self.package_info,
            'clientathome': self.client_at_home,
            'warning': self.warning,
        }
    
    @classmethod
    def from_json(cls, data: dict) -> 'Destination':
        """Créer depuis un dict/JSON (format Flutter)"""
        return cls(
            id=data['id'],
            name=data['name'],
            latitude=float(data['latitude']),
            longitude=float(data['longitude']),
            additional_info=data.get('additionalInfo'),
            is_completed=data.get('isCompleted', False),
            client_name=data.get('clientName'),
            package_info=data.get('packageInfo'),
            client_at_home=data.get('clientathome', False),
            warning=data.get('warning', False),
        )
