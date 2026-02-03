import logging
import asyncio
from typing import Optional, Callable
from .Trip import Trip

logger = logging.getLogger("trip-listener")


class TripListener:
    """Écoute les mises à jour de trips depuis Flutter via Data Channel"""
    
    def __init__(self):
        self.callbacks: list[Callable[[Trip], None]] = []
        self.is_running = False
    
    async def start(self) -> None:
        """Démarre le listener en mode passif (écoute via data_received)"""
        self.is_running = True
        logger.info("🎧 TripListener démarré en mode passif")
    
    async def stop(self) -> None:
        """Arrête le listener"""
        self.is_running = False
        logger.info("⏹️ TripListener arrêté")
    
    def on_trip_update(self, callback: Callable[[Trip], None]) -> None:
        """Enregistre un callback pour les mises à jour de trips
        
        Args:
            callback: Fonction appelée avec un objet Trip lors d'une mise à jour
        """
        self.callbacks.append(callback)
        logger.info(f"✅ Callback enregistré ({len(self.callbacks)} total)")
    
    async def receive_data(self, trip_data: dict) -> None:
        """Reçoit les données d'un trip depuis Flutter et notifie les callbacks
        
        Args:
            trip_data: Dictionnaire contenant les données du trip
        """
        if not self.is_running:
            logger.warning("⚠️ Listener non démarré, données ignorées")
            return
        
        try:
            # Convertit le dict en objet Trip
            trip = Trip.from_dict(trip_data)
            
            # Notifie tous les callbacks
            for callback in self.callbacks:
                try:
                    callback(trip)
                except Exception as e:
                    logger.error(f"❌ Erreur dans callback: {e}", exc_info=True)
        
        except Exception as e:
            logger.error(f"❌ Erreur conversion Trip: {e}", exc_info=True)


# Instance globale (Singleton)
_listener: Optional[TripListener] = None


def get_trip_listener() -> TripListener:
    """Retourne l'instance globale du listener"""
    global _listener
    if _listener is None:
        _listener = TripListener()
    return _listener
