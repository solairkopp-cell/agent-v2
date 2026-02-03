import re
import asyncio
import json
from enum import Enum
from dataclasses import dataclass
from typing import Optional, List
from dotenv import load_dotenv

from livekit import agents, rtc
from livekit.agents import AgentServer, AgentSession, Agent, room_io
from livekit.plugins import noise_cancellation, silero
from livekit.agents.llm import ChatContext
from destination import Destination

load_dotenv(".env.local")


# ==================== CONFIGURATION ====================

class Mode(Enum):
    """États de l'agent"""
    NORMAL = "normal"
    DELIVERY_CONFIRMATION = "delivery_confirmation"


class ConfirmationState(Enum):
    """Sous-états lors de la confirmation"""
    ASKING_COMPLETION = "asking_completion"
    WAITING_PHOTO = "waiting_photo"
    ASKING_REASON = "asking_reason"
    WAITING_REASON_DETAIL = "waiting_reason_detail"


REASONS = {
    "1": "the recipient was absent",
    "2": "no safe place to leave the package",
    "3": "access not possible (closed door, intercom, secured building)",
    "4": "address not found or incorrect",
    "5": "the recipient refused the delivery",
    "6": "another reason"
}

CONFIRMATION_KEYWORDS = re.compile(r"\b(yes|yeah|yep|done|completed|delivered)\b", re.I)
REJECTION_KEYWORDS = re.compile(r"\b(no|nope|not|never)\b", re.I)


# ==================== AGENT STATE ====================

@dataclass
class AgentState:
    """État centralisé de l'agent"""
    mode: Mode = Mode.NORMAL
    confirmation_state: Optional[ConfirmationState] = None
    current_delivery: Optional[Destination] = None
    destinations: List[Destination] = None
    first_launch: bool = True
    pending_reason_number: Optional[str] = None
    
    def __post_init__(self):
        if self.destinations is None:
            self.destinations = []
    
    def reset_delivery_state(self):
        """Reset après confirmation/infirmation"""
        self.mode = Mode.NORMAL
        self.confirmation_state = None
        self.current_delivery = None
        self.pending_reason_number = None
    
    def get_next_delivery(self) -> Optional[Destination]:
        """Retourne la prochaine livraison non complétée"""
        for dest in self.destinations:
            if not dest.is_completed:
                return dest
        return None
    
    def mark_completed(self, delivery_id: str):
        """Marque une livraison comme complétée"""
        self.destinations = [
            d.copy_with(is_completed=True) if d.id == delivery_id else d
            for d in self.destinations
        ]


# ==================== ASSISTANT ====================

class RytleAssistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="""
You are RYTLE, a professional voice assistant for delivery drivers.
You are extremely concise. Use short sentences. Only the essential.
You speak English only.
"""
        )


# ==================== MESSAGE BUILDER ====================

class MessageBuilder:
    """Construction des messages système pour le LLM"""
    
    @staticmethod
    def greeting(total: int, first_delivery: Optional[Destination]) -> str:
        msg = f"Great the the driver and inform him about the  {total} deliveries today."
        if first_delivery:
            msg += f" First delivery: {first_delivery.client_name or 'Unknown client'} at {first_delivery.name}."
            if first_delivery.warning and first_delivery.additional_info:
                msg += f" WARNING: {first_delivery.additional_info}"
        return msg
    
    @staticmethod
    def next_delivery(delivery: Destination) -> str:
        msg = f"Inform the driver about the Next delivery: {delivery.client_name or 'Unknown client'} at {delivery.name}. Package: {delivery.package_info or 'N/A'}."
        if delivery.warning and delivery.additional_info:
            msg += f" WARNING: {delivery.additional_info}"
        return msg
    
    @staticmethod
    def arrival_client_home() -> str:
        return "The driver is arrived. Ask if the delivery is completed"
    
    @staticmethod
    def arrival_client_not_home() -> str:
        return "The driver is arrived but the client is not at home , inform the driver that the client is not at home and and to leave the package in a secure place like a garden for example "
    
    @staticmethod
    def ask_photo() -> str:
        return "ask the driver to take a photo of the package"
    
    @staticmethod
    def list_reasons() -> str:
        # Format clair avec pauses entre chaque raison
        return (
            "the package could not be deliverd so list the following reason , and ask him to choose one by number "
            "Number one: the recipient was absent. "
            "Number two: no safe place to leave the package. "
            "Number three: access not possible. "
            "Number four: address not found. "
            "Number five: the recipient refused. "
            "Number six: another reason. "
        )
    
    @staticmethod
    def ask_reason_detail() -> str:
        return "the driver could not deliver his package ask him to  explain the reason."
    
    @staticmethod
    def confirmed() -> str:
        return "the Delivery is  confirmed. inform the driver about that"
    
    @staticmethod
    def normal_mode(destinations: List[Destination]) -> str:
        pending = sum(1 for d in destinations if not d.is_completed)
        return f"Normal mode. Answer ONLY questions about deliveries. the driver have {pending} pending deliveries. Be concise."




class SpeechService:
    def __init__(self, session: AgentSession):
        self.session = session
        self.lock = asyncio.Lock()
        self.current_task: Optional[asyncio.Task] = None

    async def speak(self, text: str, interruptible: bool = True):
        """
        Parle le texte.
        - Si interruptible=True, une nouvelle phrase peut interrompre celle en cours.
        - Si interruptible=False, bloque jusqu'à fin de lecture.
        """
        async with self.lock:
            chat_ctx = ChatContext()
            chat_ctx.add_message(role="system", content=text)

            # Si interruptible, on peut lancer en tâche détachée
            if interruptible:
                # Lance le TTS mais ne bloque pas l'appelant
                self.current_task = asyncio.create_task(
                    self.session.generate_reply(chat_ctx=chat_ctx, allow_interruptions=True)
                )
                await self.current_task  # optionnel, ou juste laisser en tâche de fond
            else:
                # Non-interruptible → on attend la fin
                await self.session.generate_reply(chat_ctx=chat_ctx, allow_interruptions=False)


# ==================== EVENT HANDLERS ====================

class EventHandler:
    """Gestion des événements reçus du client"""
    
    def __init__(self, state: AgentState, session: AgentSession, ctx,speech: SpeechService):
        self.state = state
        self.session = session
        self.ctx = ctx
        self.speech = speech
    
    async def handle_arrival(self, delivery_id: str):
        """Gestion du signal 'arrived'"""
        print(f"\n🚚 ARRIVAL SIGNAL for delivery #{delivery_id}")
        
        # Trouver la livraison
        delivery = next((d for d in self.state.destinations if d.id == delivery_id), None)
        if not delivery:
            print(f"⚠️ Delivery #{delivery_id} not found")
            return
        
        # Basculer en mode confirmation
        self.state.mode = Mode.DELIVERY_CONFIRMATION
        self.state.current_delivery = delivery
        
        # Vérifier si client à la maison
        if delivery.client_at_home:
            # CAS A : Client présent
            print("🏠 Client at home - asking for completion")
            self.state.confirmation_state = ConfirmationState.ASKING_COMPLETION
            await self.speech.speak(MessageBuilder.arrival_client_home(),False)
        else:
            # CAS B : Client absent
            print("📦 Client not at home - requesting photo")
            self.state.confirmation_state = ConfirmationState.WAITING_PHOTO
            
            # IMPORTANT : D'abord annoncer, PUIS envoyer le signal
            await self.speech.speak(MessageBuilder.arrival_client_not_home(),False)
            await asyncio.sleep(0.8)  # Pause pour laisser l'agent parler
            await self.speech.speak(MessageBuilder.ask_photo(),False)
            await asyncio.sleep(0.3)  # Petite pause avant le signal
            
            # Envoyer signal ask_photo APRÈS l'annonce vocale
            await self._publish_event({
                "type": "ask_photo",
                "delivery_id": delivery.id
            })
            print("📸 Photo request signal sent")
    
    async def handle_photo_taken(self):
        """Gestion du signal 'photo_taken'"""
        if self.state.mode != Mode.DELIVERY_CONFIRMATION or not self.state.current_delivery:
            print("⚠️ photo_taken received but not in delivery mode")
            return
        
        print("📸 Photo received - confirming delivery")
        await self._confirm_delivery()
    
    async def handle_photo_not_taken(self):
        """Gestion du signal 'photo_not_taken'"""
        if self.state.mode != Mode.DELIVERY_CONFIRMATION or not self.state.current_delivery:
            print("⚠️ photo_not_taken received but not in delivery mode")
            return
        
        print("❌ Photo not taken - asking reason")
        self.state.confirmation_state = ConfirmationState.ASKING_REASON
        await self.speech.speak(MessageBuilder.list_reasons())
    
    async def handle_destinations_update(self, destinations_data: List[dict]):
        """Mise à jour de la liste complète des destinations"""
        self.state.destinations.clear()
        for dest_json in destinations_data:
            try:
                self.state.destinations.append(Destination.from_json(dest_json))
            except Exception as e:
                print(f"❌ Error parsing destination: {e}")
        
        print(f"✅ {len(self.state.destinations)} destinations loaded")
    
    async def handle_add_destination(self, destination_data: dict):
        """Ajoute une destination à la liste"""
        try:
            destination = Destination.from_json(destination_data)
            
            # Vérifier si elle existe déjà (par ID)
            existing_index = next(
                (i for i, d in enumerate(self.state.destinations) if d.id == destination.id),
                None
            )
            
            if existing_index is not None:
                # Remplacer si existe déjà
                self.state.destinations[existing_index] = destination
                print(f"🔄 Destination #{destination.id} updated: {destination.name}")
            else:
                # Ajouter si nouvelle
                self.state.destinations.append(destination)
                print(f"➕ Destination #{destination.id} added: {destination.name}")
        
        except Exception as e:
            print(f"❌ Error adding destination: {e}")
    
    async def handle_remove_destination(self, delivery_id: str):
        """Retire une destination de la liste"""
        initial_count = len(self.state.destinations)
        self.state.destinations = [
            d for d in self.state.destinations if d.id != delivery_id
        ]
        
        if len(self.state.destinations) < initial_count:
            print(f"➖ Destination #{delivery_id} removed")
        else:
            print(f"⚠️ Destination #{delivery_id} not found")
    
    async def _confirm_delivery(self):
        """Confirmer la livraison et passer à la suivante"""
        delivery_id = self.state.current_delivery.id
        
        # Publier confirmation
        await self._publish_event({
            "type": "delivery_confirmed",
            "delivery_id": delivery_id
        })
        
        # Marquer comme complétée
        self.state.mark_completed(delivery_id)
        
        # Reset état
        self.state.reset_delivery_state()
        
        # Annoncer confirmation + prochaine livraison
        await self.speech.speak(MessageBuilder.confirmed(),False)
        
        next_delivery = self.state.get_next_delivery()
        if next_delivery:
            await asyncio.sleep(0.3)
            await self.speech.speak(MessageBuilder.next_delivery(next_delivery),False)
        else:
            await self.speech.speak("Inform the driver that all deliveries has been completed",False)
    
    async def _infirm_delivery(self, reason: str):
        """Infirmer la livraison avec raison"""
        delivery_id = self.state.current_delivery.id
        
        # Publier infirmation
        await self._publish_event({
            "type": "delivery_not_confirmed",
            "delivery_id": delivery_id,
            "reason": reason
        })
        self.state.mark_completed(delivery_id)
        # Reset état (ne pas marquer comme complétée)
        self.state.reset_delivery_state()
        
        await self.speech.speak("inform the driver that the delivery has benn marked as not completed and  Reason noted.",False)
        
        # Annoncer prochaine livraison
        next_delivery = self.state.get_next_delivery()
        if next_delivery:
            await asyncio.sleep(0.3)
            await self.speech.speak(MessageBuilder.next_delivery(next_delivery),False)
    
    
    async def _publish_event(self, data: dict):
        """Publier un événement au client"""
        try:
            await self.ctx.room.local_participant.publish_data(
                json.dumps(data).encode("utf-8"),
                reliable=True
            )
        except Exception as e:
            print(f"❌ Failed to publish event: {e}")


# ==================== SPEECH HANDLER ====================

class SpeechHandler:
    """Gestion de la parole utilisateur"""
    
    def __init__(self, state: AgentState, session: AgentSession, event_handler: EventHandler,speech: SpeechService):
        self.state = state
        self.session = session
        self.event_handler = event_handler
        self.speech = speech  
    
    async def handle_user_speech(self, text: str):
        """Traite la parole de l'utilisateur selon le mode"""
        print(f"\n🎤 USER: '{text}'")
        
        # GREETING AU PREMIER LANCEMENT
        if self.state.first_launch:
            self.state.first_launch = False
            await self._initial_greeting()
            return
        
        # MODE CONFIRMATION DE LIVRAISON
        if self.state.mode == Mode.DELIVERY_CONFIRMATION:
            await self._handle_confirmation_mode(text)
        
        # MODE NORMAL (questions sur livraisons)
        else:
            await self._handle_normal_mode(text)
    
    async def _initial_greeting(self):
        """Salutation initiale"""
        total = len(self.state.destinations)
        first = self.state.get_next_delivery()
        await self.speech.speak(MessageBuilder.greeting(total, first),interruptible=False)
    
    async def _handle_confirmation_mode(self, text: str):
        """Gestion du mode confirmation"""
        state = self.state.confirmation_state
        
        # ATTENTE DE PHOTO (ne rien faire, attendre signal)
        if state == ConfirmationState.WAITING_PHOTO:
            print("⏳ Waiting for photo signal, ignoring speech")
            return
        
        # DEMANDE SI LIVRAISON COMPLÉTÉE (client at home)
        elif state == ConfirmationState.ASKING_COMPLETION:
            if CONFIRMATION_KEYWORDS.search(text):
                print("✅ Delivery confirmed by driver")
                await self.event_handler._confirm_delivery()
            
            elif REJECTION_KEYWORDS.search(text):
                print("❌ Delivery not completed - asking reason")
                self.state.confirmation_state = ConfirmationState.ASKING_REASON
                await self.speech.speak(MessageBuilder.list_reasons())
            
            else:
                # Reboucler
                await self.speech.speak("ask the driver to Please answer yes or no. and ask if the delivery is completed")
        
        # ATTENTE DU NUMÉRO DE RAISON
        elif state == ConfirmationState.ASKING_REASON:
            # Chercher un numéro dans la réponse
            number = self._extract_number(text)
            
            if number in REASONS:
                if number == "6":  # "autre raison"
                    print("📝 Reason 6 (other) selected - asking detail")
                    self.state.pending_reason_number = number
                    self.state.confirmation_state = ConfirmationState.WAITING_REASON_DETAIL
                    await self.speech.speak(MessageBuilder.ask_reason_detail(),False)
                else:
                    print(f"📝 Reason {number} selected")
                    reason = REASONS[number]
                    await self.event_handler._infirm_delivery(reason)
            else:
                # Reboucler
                await self.speech.speak(MessageBuilder.list_reasons())
        
        # ATTENTE DU DÉTAIL DE LA RAISON
        elif state == ConfirmationState.WAITING_REASON_DETAIL:
            reason_detail = text.strip()
            if reason_detail:
                print(f"📝 Custom reason received: {reason_detail}")
                await self.event_handler._infirm_delivery(reason_detail)
            else:
                await self.speech.speak("ask the driver to Please explain the reason.")
    
    async def _handle_normal_mode(self, text: str):
        """Gestion du mode normal (questions)"""
        # Vérifier si c'est une question
        if not self._is_question(text):
            print("ℹ️ Not a question, ignoring")
            return
        
        # Construire le contexte
        chat_ctx = ChatContext()
        
        # Instructions système
        chat_ctx.add_message(
            role="system",
            content=MessageBuilder.normal_mode(self.state.destinations)
        )
        
        # Injecter les destinations comme contexte
        if self.state.destinations:
            destinations_json = [d.to_json() for d in self.state.destinations]
            chat_ctx.add_message(
                role="assistant",
                content=f"[CONTEXT] {json.dumps(destinations_json)}"
            )
        
        # Question de l'utilisateur
        chat_ctx.add_message(role="user", content=text)
        
        # Générer réponse
        await self.session.generate_reply(
            chat_ctx=chat_ctx,
            allow_interruptions=True
        )
    
    def _is_question(self, text: str) -> bool:
        """Détermine si le texte est une question"""
        # Nettoyer le texte (enlever espaces multiples, tout en minuscules)
        text_clean = " ".join(text.lower().split())
        
        # Mots interrogatifs
        question_words = [
            "what", "who", "where", "when", "why", "how", "which",
            "is", "are", "am", "was", "were",
            "do", "does", "did", "done",
            "can", "could", "should", "would", "will",
            "have", "has", "had","hello"
        ]
        
        # Vérifier si ça se termine par "?"
        if text.strip().endswith("?"):
            return True
        
        # Vérifier si ça commence par un mot interrogatif
        for word in question_words:
            if text_clean.startswith(word + " ") or text_clean == word:
                return True
        
        # Patterns de questions courantes
        question_patterns = [
            "any delivery", "any deliveries",
            "how many", "tell me",
            "show me", "give me","is there","do the","do you","is the ","who is ","who are","i want"
        ]
        
        for pattern in question_patterns:
            if pattern in text_clean:
                return True
        
        return False
    
    def _extract_number(self, text: str) -> Optional[str]:
        """
        Extracts a delivery number (1-6) from text.
        Supports both digits and English words, returning "1"-"6".
        """
        word_map = {
            "one": "1", "two": "2", "three": "3", 
            "four": "4", "five": "5", "six": "6"
        }
        
        # Normalize text to lowercase
        text = text.lower()
        
        # 1. Look for digits 1-6
        digit_match = re.search(r'\b([1-6])\b', text)
        if digit_match:
            return digit_match.group(1)
            
        # 2. Look for words one-six
        words_pattern = r'\b(' + '|'.join(word_map.keys()) + r')\b'
        word_match = re.search(words_pattern, text)
        if word_match:
            return word_map[word_match.group(1)]
            
        return None
    





# ==================== SERVEUR ====================

server = AgentServer()

@server.rtc_session()
async def rytle_agent(ctx: agents.JobContext):
    print("\n" + "="*60)
    print("🚀 RYTLE SESSION STARTED")
    print("="*60 + "\n")
    
    # Créer session LiveKit
    session = AgentSession(
        stt="assemblyai/universal-streaming:en",
        llm="openai/gpt-4o-mini",
        tts="cartesia/sonic-3:9626c31c-bec5-4cca-baa8-f8ba9e84c8bc",
        vad=silero.VAD.load(),
        turn_detection="server_vad",
        allow_interruptions=True,
    )
    
    # État de l'agent
    state = AgentState()
    speech = SpeechService(session)
    # Handlers
    event_handler = EventHandler(state, session, ctx,speech)
    speech_handler = SpeechHandler(state, session, event_handler,speech)
    
    # ========== ÉVÉNEMENT : Parole utilisateur ==========
    @session.on("user_input_transcribed")
    def on_user_speech(event):
        if not event.is_final:
            return
        
        text = (event.transcript or "").strip()
        if not text:
            return
        
        asyncio.create_task(speech_handler.handle_user_speech(text))
    
    # ========== ÉVÉNEMENT : Données reçues ==========
    @ctx.room.on("data_received")
    def on_data(event):
        try:
            payload = json.loads(event.data.decode("utf-8"))
            event_type = payload.get("type")
            
            print(f"\n📦 EVENT RECEIVED: {event_type}")
            
            if event_type == "arrived":
                asyncio.create_task(
                    event_handler.handle_arrival(payload.get("delivery_id"))
                )
            
            elif event_type == "photo_taken":
                asyncio.create_task(event_handler.handle_photo_taken())
            
            elif event_type == "photo_not_taken":
                asyncio.create_task(event_handler.handle_photo_not_taken())
            
            elif event_type == "destinations_update":
                asyncio.create_task(
                    event_handler.handle_destinations_update(payload.get("destinations", []))
                )
            
            elif event_type == "add_destination":
                asyncio.create_task(
                    event_handler.handle_add_destination(payload.get("destination", {}))
                )
            
            elif event_type == "remove_destination":
                asyncio.create_task(
                    event_handler.handle_remove_destination(payload.get("delivery_id"))
                )
            
            else:
                print(f"⚠️ Unknown event type: {event_type}")
        
        except Exception as e:
            print(f"❌ Error handling data: {e}")
    
    # Démarrer l'agent
    await session.start(
        room=ctx.room,
        agent=RytleAssistant(),
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=lambda params: (
                    noise_cancellation.BVCTelephony()
                    if params.participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
                    else noise_cancellation.BVC()
                ),
            ),
        ),
    )
    
    print("\n✅ RYTLE IS READY")
    print("   - Send 'destinations_update' for full list")
    print("   - Send 'add_destination' to add one by one")
    print("   - Send 'remove_destination' to remove")
    print("   - Listening for arrival signals")
    print("   - Answering delivery questions\n")


if __name__ == "__main__":
    agents.cli.run_app(server)