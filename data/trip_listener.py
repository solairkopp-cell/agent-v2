import asyncio
import logging
from typing import Optional, Callable, List
import json
from .models import Trip

logger = logging.getLogger("trip-listener")


class TripListener:
    """Service qui écoute et reçoit les nouvelles données de trips en temps réel"""
    
    def __init__(self):
        self.callbacks: List[Callable[[Trip], None]] = []
        self._running = False
        self._listener_task: Optional[asyncio.Task] = None
    
    def on_trip_update(self, callback: Callable[[Trip], None]) -> None:
        """Enregistre une fonction à appeler quand des données arrivent
        
        Args:
            callback: Fonction qui prend un Trip en paramètre
        """
        self.callbacks.append(callback)
        logger.info("Callback enregistré")
    
    async def receive_data(self, data: dict) -> None:
        """Reçoit des données externes et notifie les callbacks
        
        Args:
            data: Données du trip (dict Flutter)
        """
        try:
            # Conversion dict → objet Trip
            trip = Trip.from_dict(data)
            logger.info(f"Trip converti: {trip}")
            
            # Notifie tous les callbacks avec l'objet Trip
            for callback in self.callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(trip)
                    else:
                        callback(trip)
                except Exception as e:
                    logger.error(f"Erreur callback: {e}", exc_info=True)
                    
        except Exception as e:
            logger.error(f"Erreur conversion Trip: {e}", exc_info=True)
    
    async def start(self, source_url: Optional[str] = None) -> None:
        """Démarre l'écoute des données
        
        Args:
            source_url: URL de la source de données (WebSocket, API, etc.)
        """
        if self._running:
            logger.warning("Déjà en écoute")
            return
        
        self._running = True
        logger.info("Démarrage de l'écoute...")
        
        if source_url:
            self._listener_task = asyncio.create_task(self._listen_websocket(source_url))
        else:
            logger.info("Mode passif: utilisez receive_data() pour envoyer des données")
    
    async def stop(self) -> None:
        """Arrête l'écoute"""
        self._running = False
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        logger.info("Écoute arrêtée")
    
    async def _listen_websocket(self, ws_url: str) -> None:
        """Écoute un WebSocket pour les mises à jour
        
        Args:
            ws_url: URL du WebSocket
        """
        import aiohttp
        
        while self._running:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(ws_url) as ws:
                        logger.info(f"Connecté à {ws_url}")
                        
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                data = json.loads(msg.data)
                                await self.receive_data(data)
                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                logger.error(f"Erreur WebSocket: {ws.exception()}")
                                break
                                
            except Exception as e:
                logger.error(f"Erreur connexion: {e}")
                await asyncio.sleep(5)


# Instance globale (Singleton)
_listener: Optional[TripListener] = None


def get_trip_listener() -> TripListener:
    """Retourne l'instance globale du listener"""
    global _listener
    if _listener is None:
        _listener = TripListener()
    return _listener