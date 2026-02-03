from dataclasses import dataclass
from typing import Optional
from .location import Location
from .trip_state import TripState

@dataclass
class Trip:
    """Represents a trip object in the database"""
    id: str
    address: str
    location: Location
    state: TripState
    client_name: Optional[str] = None
    package_info: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Trip':
        """Create Trip from dict (Flutter format)
        
        Args:
            data: Dictionary containing trip data
            
        Returns:
            Trip object
        """
        location_data = data.get('location', {})
        state_str = data.get('state', 'notStarted')
        
        return cls(
            id=data['id'],
            address=data['address'],
            location=Location.from_dict(location_data),
            state=TripState.from_string(state_str),
            client_name=data.get('clientName'),
            package_info=data.get('packageInfo'),
        )
    
    def to_dict(self) -> dict:
        """Convert Trip to dict for JSON serialization
        
        Returns:
            Dictionary representation
        """
        return {
            'id': self.id,
            'address': self.address,
            'location': self.location.to_dict(),
            'state': self.state.value,
            'clientName': self.client_name,
            'packageInfo': self.package_info,
        }
    
    def __repr__(self) -> str:
        return f"Trip(id={self.id}, address='{self.address}', state={self.state.value})"