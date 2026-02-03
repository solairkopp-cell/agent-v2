# agent_fsm.py - Refactored agent using pure FSM approach vivi
from dotenv import load_dotenv
from livekit import agents, rtc
from livekit.agents import AgentServer, AgentSession, Agent, room_io
from livekit.agents.llm.tool_context import StopResponse
from livekit.plugins import noise_cancellation, silero
import json
import asyncio
import logging
import re
import hashlib
import time
from dataclasses import dataclass
from typing import Optional, Callable

from agent_helper.enums import AgentMode, Event, TreatmentState
from delivery_treatment import DeliveryTreatmentFSM
from tools import (
    get_current_time, get_trip_count, get_trip_info, list_active_trips,
    set_trip_state_to_completed, set_trip_state_to_in_progress,
    set_trip_state_to_not_started, set_trip_state_to_cancelled,
    list_all_trips, send_message, send_ask_photo_event,
    send_Trip_update_event, send_trip_started_event,
    send_trip_completed_event, send_trip_cancelled_event,
    complete_delivery, handle_failed_delivery,
)

from data.models.trip_listener import get_trip_listener
from data.models.trip_store import get_trip_store
from data.models.trip_state import TripState

# Import FSM and domain models


load_dotenv(".env.local")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voice-agent")

# ---------- Parsing helpers ----------
POSITIVE_RE = re.compile(r"\b(yes|yep|yeah|done|completed|delivered)\b", re.I)
NEGATIVE_RE = re.compile(r"\b(no|nope|not|never)\b", re.I)


@dataclass
class AgentState:
    """Minimal agent state - FSM handles delivery logic"""
    mode: AgentMode = AgentMode.NORMAL
    current_trip_id: Optional[str] = None
    
    def reset(self):
        """Reset to normal mode"""
        self.mode = AgentMode.NORMAL
        self.current_trip_id = None


class SessionLog:
    """Simple logger for session events"""
    def __init__(self):
        self.events = []
    
    def add_event(self, message: str):
        timestamp = __import__('datetime').datetime.now().isoformat()
        event = f"[{timestamp}] {message}"
        self.events.append(event)
        logger.info(event)
    
    def get_log(self) -> str:
        return "\n".join(self.events)


class SpeechService:
    """Manages TTS with chat context"""
    def __init__(self, session: AgentSession, chat_ctx):
        self.session = session
        self.chat_ctx = chat_ctx
        self.audio_lock = asyncio.Lock()
        self.current_task = None  # SpeechHandle

    async def say(self, text: str, allow_interruptions: bool = False):
        async with self.audio_lock:
            self.current_task = self.session.say(
                text=text,
                add_to_chat_ctx=False,
                allow_interruptions=allow_interruptions
            )



class SessionManager:
    """Manages session lifecycle and cleanup"""
    def __init__(self, ctx, session, speech, session_log):
        self.ctx = ctx
        self.session = session
        self.speech = speech
        self.session_log = session_log
        self.closed = False
    
    async def terminate(self, reason: str = "normal_end"):
        if self.closed:
            return
        self.closed = True
        self.session_log.add_event(f"SESSION TERMINATION: {reason}")
        
        # Stop TTS
        if getattr(self.speech, "current_task", None) and not self.speech.current_task.done():
            try:
                self.speech.current_task.cancel()
            except Exception:
                pass
        
        # Close session
        try:
            await self.session.aclose()
            self.session_log.add_event("Agent session closed")
        except Exception as e:
            self.session_log.add_event(f"Agent session close error: {e}")
        
        # Disconnect room
        try:
            await self.ctx.room.disconnect()
            self.session_log.add_event("Room disconnected")
        except Exception as e:
            self.session_log.add_event(f"Room disconnect error: {e}")
        
        # Delete room (release quota)
        try:
            from livekit.protocol.room import DeleteRoomRequest
            await self.ctx.api.room.delete_room(DeleteRoomRequest(room=self.ctx.room.name))
            self.session_log.add_event("Room deleted successfully (quota released)")
        except Exception as e:
            self.session_log.add_event(f"Room deletion error: {e}")


class Assistant(Agent):
    def __init__(
        self,
        *,
        speech: SpeechService,
        state: AgentState,
        delivery_fsm: DeliveryTreatmentFSM,
        session_log: SessionLog,
        make_event_id: Callable[[Optional[str], str], str],
        extract_number: Callable[[str], Optional[str]],
    ) -> None:
        super().__init__(
            instructions="""You are RYTLE, a friendly assistant for delivery drivers.
            Respond in 2 sentences max. You have access to tools.
            Don't ask permission to update trip status - do it automatically.""",
            tools=[
                get_current_time, get_trip_count, get_trip_info, list_active_trips,
                set_trip_state_to_completed, set_trip_state_to_in_progress,
                set_trip_state_to_not_started, set_trip_state_to_cancelled,
                list_all_trips, send_message, send_ask_photo_event,
                send_Trip_update_event, send_trip_started_event,
                send_trip_completed_event, send_trip_cancelled_event,
                complete_delivery, handle_failed_delivery,
            ],
        )

        self._speech = speech
        self._state = state
        self._delivery_fsm = delivery_fsm
        self._session_log = session_log
        self._make_event_id = make_event_id
        self._extract_number = extract_number

    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:  # type: ignore[override]
        text = (new_message.text_content or "").strip()
        if not text:
            raise StopResponse()

        self._session_log.add_event(f"USER: {text}")

        # When not in treatment mode, keep the default LLM behavior.
        if self._state.mode != AgentMode.DELIVERY_TREATMENT:
            return

        normalized = text.lower()
        current = self._delivery_fsm.get_state()

        # We own the conversation while in treatment mode: never let the LLM reply.
        if current == TreatmentState.ASK_DELIVERY_COMPLETION:
            if POSITIVE_RE.search(normalized):
                await self._delivery_fsm.handle_event(
                    Event.CONFIRM_YES,
                    {},
                    event_id=self._make_event_id(self._state.current_trip_id, "voice_yes"),
                )
            elif NEGATIVE_RE.search(normalized):
                await self._delivery_fsm.handle_event(
                    Event.CONFIRM_NO,
                    {},
                    event_id=self._make_event_id(self._state.current_trip_id, "voice_no"),
                )
            else:
                # Loop until we get an expected answer.
                await self._delivery_fsm.reprompt()

            raise StopResponse()

        if current == TreatmentState.ASK_NON_DELIVERY_REASON:
            number = self._extract_number(text)
            if number:
                await self._delivery_fsm.handle_event(
                    Event.REASON_NUMBER,
                    {"number": number},
                    event_id=self._make_event_id(self._state.current_trip_id, f"reason_{number}"),
                )
            else:
                await self._delivery_fsm.reprompt()

            raise StopResponse()

        if current == TreatmentState.ASK_REASON_DETAIL:
            await self._delivery_fsm.handle_event(
                Event.REASON_TEXT,
                {"text": text},
                event_id=self._make_event_id(self._state.current_trip_id, "reason_text"),
            )
            raise StopResponse()

        if current == TreatmentState.ASK_PHOTO:
            # Photo normally comes from Flutter events. If the driver speaks, keep it deterministic.
            await self._delivery_fsm.reprompt()
            raise StopResponse()

        raise StopResponse()


server = AgentServer()


@server.rtc_session()
async def my_agent(ctx: agents.JobContext):
    listener = get_trip_listener()
    store = get_trip_store()
    
    # Session log
    session_log = SessionLog()
    session_log.add_event("RYTLE SESSION STARTED")
    
    # Agent session
    session = AgentSession(
        stt="assemblyai/universal-streaming:en",
        llm="openai/gpt-4o-mini",
        tts="cartesia/sonic-3:9626c31c-bec5-4cca-baa8-f8ba9e84c8bc",
        vad=silero.VAD.load(),
    )
    
    # Speech service
    speech = SpeechService(session, session._chat_ctx)
    
    # Session manager
    session_manager = SessionManager(ctx, session, speech, session_log)
    
    # Agent state (minimal)
    state = AgentState()
    
    # ------------------ Helpers ------------------
    
    async def publish_event_to_flutter(payload: dict):
        """Publish JSON event to Flutter"""
        try:
            await ctx.room.local_participant.publish_data(
                json.dumps(payload).encode("utf-8"),
                reliable=True
            )
            logger.info("Published event to Flutter: %s", payload.get("type"))
        except Exception as e:
            logger.exception("Failed to publish event: %s", e)
    
    async def mark_trip_completed_and_notify(trip_id: str):
        """Mark trip as completed"""
        trip = store.get(trip_id)
        if not trip:
            logger.warning("mark_trip_completed: trip not found %s", trip_id)
            return
        
        trip.state = TripState.COMPLETED
        store.update(trip)
        
        await publish_event_to_flutter({
            "type": "trip_completed_event",
            "trip_id": trip_id,
            "address": trip.address,
            "client_name": trip.client_name,
            "timestamp": __import__('datetime').datetime.now().isoformat()
        })
        
        logger.info("Trip completed: %s", trip_id)
        session_log.add_event(f"Trip completed: {trip_id}")
        
        state.reset()
        await speech.say("the Delivery is confirmed. inform the driver about that", allow_interruptions=False)
    
    async def mark_trip_failed_and_notify(trip_id: str, reason: str):
        """Mark trip as failed"""
        trip = store.get(trip_id)
        if not trip:
            logger.warning("mark_trip_failed: trip not found %s", trip_id)
            return
        
        trip.state = TripState.CANCELLED
        
        try:
            setattr(trip, "failure_reason", reason)
        except Exception:
            pass
        
        store.update(trip)
        
        await publish_event_to_flutter({
            "type": "trip_cancelled_event",
            "trip_id": trip_id,
            "address": trip.address,
            "reason": reason,
            "timestamp": __import__('datetime').datetime.now().isoformat()
        })
        
        logger.info("Trip failed: %s (reason=%s)", trip_id, reason)
        session_log.add_event(f"Trip failed: {trip_id} - {reason}")
        
        state.reset()
        await speech.say("inform the driver that the delivery has been marked as not completed and Reason noted.", allow_interruptions=False)
    
    def extract_number(text: str) -> Optional[str]:
        """Extract number 1-6 from text"""
        word_map = {
            "one": "1", "two": "2", "three": "3",
            "four": "4", "five": "5", "six": "6"
        }
        
        text = text.lower()
        
        # Look for digit
        digit_match = re.search(r'\b([1-6])\b', text)
        if digit_match:
            return digit_match.group(1)
        
        # Look for word
        words_pattern = r'\b(' + '|'.join(word_map.keys()) + r')\b'
        word_match = re.search(words_pattern, text)
        if word_match:
            return word_map[word_match.group(1)]
        
        return None
    
    def make_event_id(trip_id: Optional[str], event_type: str) -> str:
        """Generate unique event ID for idempotency"""
        base = f"{trip_id or 'no-trip'}:{event_type}:{time.time_ns()}"
        return hashlib.sha256(base.encode()).hexdigest()[:16]
    
    # Sync wrappers for FSM
    def mark_completed_sync(trip_id: str):
        asyncio.create_task(mark_trip_completed_and_notify(trip_id))
    
    def mark_failed_sync(trip_id: str, reason: str):
        asyncio.create_task(mark_trip_failed_and_notify(trip_id, reason))
    
    async def tts_say(text: str):
        await speech.say(text, allow_interruptions=False)
    
    # Initialize FSM (no more set_mode dependency) (no more set_mode dependency)
    delivery_fsm = DeliveryTreatmentFSM(
        tts_say=tts_say,
        publish_event=publish_event_to_flutter,
        mark_completed=mark_completed_sync,
        mark_failed=mark_failed_sync
    )

    assistant = Assistant(
        speech=speech,
        state=state,
        delivery_fsm=delivery_fsm,
        session_log=session_log,
        make_event_id=make_event_id,
        extract_number=extract_number,
    )
    
    # ------------------ Data channel handler ------------------
    
    async def handle_data_received(data_packet):
        """Process messages from Flutter"""
        try:
            message = json.loads(data_packet.data.decode("utf-8"))
            event_type = message.get("type")
            
            # Trip update
            if event_type == "trip_update":
                await listener.receive_data(message.get("data"))
                return
            
            # Delivery treatment finished (FSM -> Agent event)
            if event_type == "delivery_treatment_finished":
                trip_id = message.get("trip_id")
                success = message.get("success", False)
                logger.info(f"Treatment finished for {trip_id} - success: {success}")
                session_log.add_event(f"Treatment finished: {trip_id} (success={success})")
                
                # Agent reacts to FSM completion
                state.mode = AgentMode.NORMAL
                state.reset()
                delivery_fsm.cleanup()
                return
            
            # Arrival -> start FSM treatment
            if event_type in ("destination_arrival", "arrived"):
                trip_id = (message.get("id") or message.get("trip_id") or message.get("delivery_id"))
                if not trip_id:
                    logger.warning("arrival without trip_id")
                    return
                
                # Update state
                state.current_trip_id = trip_id
                state.mode = AgentMode.DELIVERY_TREATMENT
                session_log.add_event(f"Arrival at trip {trip_id}")
                
                # Get address
                address = message.get("address")
                if not address:
                    trip = store.get(trip_id)
                    address = getattr(trip, "address", "") if trip else ""
                
                # Start FSM treatment
                await delivery_fsm.start_treatment(trip_id, address)
                return
            
            # Photo taken
            if event_type == "photo_taken":
                trip_id = state.current_trip_id or message.get("trip_id")
                event_id = make_event_id(trip_id, "photo_taken")
                await delivery_fsm.handle_event(Event.PHOTO_TAKEN, {}, event_id=event_id)
                return
            
            # Photo not taken
            if event_type == "photo_not_taken":
                trip_id = state.current_trip_id or message.get("trip_id")
                event_id = make_event_id(trip_id, "photo_not_taken")
                await delivery_fsm.handle_event(Event.PHOTO_NOT_TAKEN, {}, event_id=event_id)
                return
            
            logger.debug("Unknown event: %s", event_type)
        
        except json.JSONDecodeError as e:
            logger.error("JSON decode error: %s", e)
        except Exception:
            logger.exception("Error in handle_data_received")
    
    @ctx.room.on("data_received")
    def _on_data_received_sync(data_packet):
        asyncio.create_task(handle_data_received(data_packet))
    
    # Handle participant disconnect
    @ctx.room.on("participant_disconnected")
    def _on_participant_disconnected(participant):
        if participant.identity != ctx.room.local_participant.identity:
            logger.info("User disconnected: %s", participant.identity)
            session_log.add_event(f"User disconnected: {participant.identity}")
            asyncio.create_task(session_manager.terminate("user_disconnected"))
    
    # ------------------ Trip listener ------------------
    
    def on_trip_update(trip):
        try:
            store.update(trip)
            logger.info("Trip updated: %s state=%s", trip.id, trip.state)
        except Exception:
            logger.exception("Error in on_trip_update")
    
    listener.on_trip_update(on_trip_update)
    await listener.start()
    
    # ------------------ Start session ------------------
    
    try:
        await session.start(
            room=ctx.room,
            agent=assistant,
            room_options=room_io.RoomOptions(
                audio_input=room_io.AudioInputOptions(
                    noise_cancellation=lambda params: (
                        noise_cancellation.BVCTelephony()
                        if params.participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
                        else noise_cancellation.BVC()
                    )
                )
            )
        )
        
        await session.generate_reply(instructions="Greet the user warmly as RYTLE and offer your assistance.")
        logger.info("Agent started. Trips in memory: %d", store.count())
        session_log.add_event(f"Agent ready - {store.count()} trips loaded")
    
    except Exception as e:
        logger.exception("Error during session: %s", e)
        session_log.add_event(f"Session error: {e}")
        await session_manager.terminate("session_error")
    
    finally:
        logger.info("Session log:\n%s", session_log.get_log())


if __name__ == "__main__":
    agents.cli.run_app(server)
