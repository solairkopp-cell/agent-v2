import logging
from typing import Optional, Dict, List
from .Trip import Trip
from .trip_state import TripState

logger = logging.getLogger("trip-store")


class TripStore:
    """Stocke et gère la liste des trips (objets Trip)"""
    
    def __init__(self):
        self.trips: Dict[str, Trip] = {}
    
    def add(self, trip: Trip) -> None:
        """Ajoute un trip
        
        Args:
            trip: L'objet Trip à ajouter
        """
        self.trips[trip.id] = trip
        logger.info(f"Trip ajouté: {trip.id} - {trip.address}")
    
    def update(self, trip: Trip) -> None:
        """Met à jour un trip
        
        Args:
            trip: L'objet Trip à mettre à jour
        """
        self.trips[trip.id] = trip
        logger.info(f"Trip mis à jour: {trip.id} - État: {trip.state.value}")
    
    def get(self, trip_id: str) -> Optional[Trip]:
        """Récupère un trip par ID
        
        Args:
            trip_id: L'ID du trip
            
        Returns:
            Le trip ou None
        """
        return self.trips.get(trip_id)
    
    def get_all(self) -> List[Trip]:
        """Récupère tous les trips
        
        Returns:
            Liste de tous les trips
        """
        return list(self.trips.values())
    
    def remove(self, trip_id: str) -> Optional[Trip]:
        """Supprime un trip
        
        Args:
            trip_id: L'ID du trip à supprimer
            
        Returns:
            Le trip supprimé ou None
        """
        removed = self.trips.pop(trip_id, None)
        if removed:
            logger.info(f"Trip supprimé: {trip_id}")
        return removed
    
    def get_by_state(self, state: TripState) -> List[Trip]:
        """Récupère les trips par état
        
        Args:
            state: L'état recherché
            
        Returns:
            Liste des trips avec cet état
        """
        return [trip for trip in self.trips.values() if trip.state == state]
    
    def get_active_trips(self) -> List[Trip]:
        """Récupère uniquement les trips en cours
        
        Returns:
            Liste des trips avec état IN_PROGRESS
        """
        return self.get_by_state(TripState.IN_PROGRESS)
    
    def get_completed_trips(self) -> List[Trip]:
        """Récupère uniquement les trips terminés
        
        Returns:
            Liste des trips avec état COMPLETED
        """
        return self.get_by_state(TripState.COMPLETED)
    
    def clear(self) -> None:
        """Vide tous les trips"""
        count = len(self.trips)
        self.trips.clear()
        logger.info(f"Tous les trips supprimés (total: {count})")
    
    def count(self) -> int:
        """Retourne le nombre total de trips
        
        Returns:
            Nombre de trips
        """
        return len(self.trips)
    
    def get_stats(self) -> dict:
        """Retourne des statistiques sur les trips
        
        Returns:
            Dict avec statistiques
        """
        all_trips = self.get_all()
        return {
            'total': len(all_trips),
            'not_started': len(self.get_by_state(TripState.NOT_STARTED)),
            'in_progress': len(self.get_by_state(TripState.IN_PROGRESS)),
            'completed': len(self.get_by_state(TripState.COMPLETED)),
            'cancelled': len(self.get_by_state(TripState.CANCELLED)),
        }


# Instance globale (Singleton)
_store: Optional[TripStore] = None


def get_trip_store() -> TripStore:
    """Retourne l'instance globale du store"""
    global _store
    if _store is None:
        _store = TripStore()
    return _store