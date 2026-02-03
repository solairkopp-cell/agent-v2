from dataclasses import dataclass
from typing import Optional

@dataclass
class Location:
    """Data model for geographical coordinates and their human-readable address"""
    latitude: float
    longitude: float
    address: str
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Location':
        """Create from dict (Flutter format)"""
        # Support both formats: direct and nested geometry
        if 'geometry' in data:
            # Google Maps API format
            geometry = data.get('geometry', {})
            location_coords = geometry.get('location', {})
            return cls(
                latitude=float(location_coords.get('lat', 0.0)),
                longitude=float(location_coords.get('lng', 0.0)),
                address=data.get('formatted_address', '')
            )
        else:
            # Simple format (from Flutter)
            return cls(
                latitude=float(data.get('latitude', 0.0)),
                longitude=float(data.get('longitude', 0.0)),
                address=data.get('address', '')
            )
    
    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization"""
        return {
            'latitude': self.latitude,
            'longitude': self.longitude,
            'address': self.address,
        }
    
    def __repr__(self) -> str:
        return f"Location(lat={self.latitude:.4f}, lng={self.longitude:.4f}, address='{self.address}')"