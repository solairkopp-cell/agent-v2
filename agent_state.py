import asyncio
from enum import Enum
from typing import Callable, Dict, Optional, Tuple, Any
import logging
logger = logging.getLogger(__name__)

# --- États et événements ---
class State(Enum):
    IDLE = "idle"
    ARRIVED = "arrived"                # asked "is delivery completed?"
    WAITING_PHOTO = "waiting_photo"
    ASKING_REASON = "asking_reason"
    WAITING_REASON_DETAIL = "waiting_reason_detail"
    COMPLETED = "completed"
    FAILED = "failed"

class Event(Enum):
    ARRIVAL = "arrival"
    YES = "yes"
    NO = "no"
    PHOTO_TAKEN = "photo_taken"
    PHOTO_NOT_TAKEN = "photo_not_taken"
    REASON_NUMBER = "reason_number"
    REASON_TEXT = "reason_text"
    TIMEOUT = "timeout"
    CANCEL = "cancel"

# Signature d'une action associée à une transition
Action = Callable[['DeliveryStateMachine', dict], Any]

# --- Machine à états ---
class DeliveryStateMachine:
    def __init__(self, *,
                 trip_id_getter: Callable[[], Optional[str]],
                 mark_completed: Callable[[str], Any],
                 mark_failed: Callable[[str, str], Any],
                 tts_say: Callable[[str], Any],
                 publish_event: Callable[[dict], Any],
                 timeout_seconds: int = 30):
        """
        Fournis les hooks métier depuis ton module principal.
        - trip_id_getter() -> current trip id
        - mark_completed(trip_id)
        - mark_failed(trip_id, reason)
        - tts_say(text)
        - publish_event(payload)
        """
        self._lock = asyncio.Lock()
        self.state: State = State.IDLE
        self.current_trip_id_getter = trip_id_getter
        self.mark_completed = mark_completed
        self.mark_failed = mark_failed
        self.tts_say = tts_say
        self.publish_event = publish_event
        self.timeout_seconds = timeout_seconds

        # transition table : (state, event) -> (next_state, action)
        self._transitions: Dict[Tuple[State, Event], Tuple[State, Action]] = {}
        self._build_transitions()

        # pour éviter double traitement d'un même event
        self._seen_event_ids = set()
        self._timeout_task: Optional[asyncio.Task] = None

    def _register(self, from_state: State, event: Event, to_state: State, action: Action):
        self._transitions[(from_state, event)] = (to_state, action)

    def _build_transitions(self):
        # ARRIVAL -> ASK completion
        self._register(State.IDLE, Event.ARRIVAL, State.ARRIVED, self._action_ask_completion)

        # ARRIVED + YES -> mark complete
        self._register(State.ARRIVED, Event.YES, State.COMPLETED, self._action_mark_complete)

        # ARRIVED + NO -> ask reason
        self._register(State.ARRIVED, Event.NO, State.ASKING_REASON, self._action_ask_reason)

        # ASKING_REASON + REASON_NUMBER -> either fail or wait for detail (6)
        self._register(State.ASKING_REASON, Event.REASON_NUMBER, State.FAILED, self._action_reason_number)

        # ASKING_REASON + REASON_TEXT (fallback)
        self._register(State.ASKING_REASON, Event.REASON_TEXT, State.FAILED, self._action_mark_failed_text)

        # If we ask for detail (6)
        self._register(State.WAITING_REASON_DETAIL, Event.REASON_TEXT, State.FAILED, self._action_mark_failed_text)

        # WAITING_PHOTO -> if PHOTO_TAKEN -> complete
        self._register(State.WAITING_PHOTO, Event.PHOTO_TAKEN, State.COMPLETED, self._action_mark_complete)

        # PHOTO_NOT_TAKEN fallback -> ask reason
        self._register(State.WAITING_PHOTO, Event.PHOTO_NOT_TAKEN, State.ASKING_REASON, self._action_ask_reason)

        # Timeout handling (generic)
        self._register(State.ARRIVED, Event.TIMEOUT, State.ASKING_REASON, self._action_ask_reason)
        self._register(State.WAITING_PHOTO, Event.TIMEOUT, State.ASKING_REASON, self._action_ask_reason)

        # Cancel
        self._register(State.ARRIVED, Event.CANCEL, State.IDLE, self._action_reset)
        self._register(State.ASKING_REASON, Event.CANCEL, State.IDLE, self._action_reset)

    async def handle_event(self, event: Event, payload: dict = None, event_id: Optional[str] = None):
        payload = payload or {}
        # idempotence
        if event_id:
            if event_id in self._seen_event_ids:
                logger.debug("Event %s already seen, skipping", event_id)
                return
            self._seen_event_ids.add(event_id)

        async with self._lock:
            key = (self.state, event)
            if key not in self._transitions:
                logger.debug("No transition defined for %s + %s", self.state, event)
                return

            next_state, action = self._transitions[key]
            logger.info("Transition %s --%s--> %s", self.state, event, next_state)
            # cancel previous timeout if any
            if self._timeout_task and not self._timeout_task.done():
                self._timeout_task.cancel()
                self._timeout_task = None

            # execute action
            res = action(payload)  # can be coroutine or sync
            if asyncio.iscoroutine(res):
                await res

            # set new state
            self.state = next_state

            # schedule timeouts for states that expect input
            if self.state in (State.ARRIVED, State.WAITING_PHOTO):
                self._timeout_task = asyncio.create_task(self._start_timeout())

    async def _start_timeout(self):
        try:
            await asyncio.sleep(self.timeout_seconds)
            # fire timeout event
            await self.handle_event(Event.TIMEOUT, {})
        except asyncio.CancelledError:
            return

    # --- Actions (async) ---
    async def _action_ask_completion(self, payload: dict):
        trip_id = self.current_trip_id_getter()
        msg = f"You have arrived at {payload.get('address','the address')}. Is the delivery completed? Please answer yes or no."
        await self.tts_say(msg)
        # remain in ARRIVED until response or timeout

    async def _action_mark_complete(self, payload: dict):
        trip_id = self.current_trip_id_getter()
        if not trip_id:
            logger.warning("mark_complete called without trip id")
            return
        # call backend
        await asyncio.to_thread(self.mark_completed, trip_id)
        await self.publish_event({"type":"trip_completed_event", "trip_id": trip_id})

    async def _action_ask_reason(self, payload: dict):
        await self.tts_say(
            "Please choose a reason by number. One: recipient absent. Two: no safe place. Three: access not possible. Four: address incorrect. Five: recipient refused. Six: another reason."
        )

    async def _action_reason_number(self, payload: dict):
        # payload expected: {"number":"1"} or {"number":"6"}
        trip_id = self.current_trip_id_getter()
        number = str(payload.get("number"))
        REASONS = {
            "1": "the recipient was absent",
            "2": "no safe place to leave the package",
            "3": "access not possible",
            "4": "address not found or incorrect",
            "5": "the recipient refused the delivery",
            # "6" handled separately
        }
        if number == "6":
            # ask for detail; move to WAITING_REASON_DETAIL manually
            self.state = State.WAITING_REASON_DETAIL
            await self.tts_say("Please explain the reason.")
            return
        reason = REASONS.get(number, "unknown reason")
        if not trip_id:
            logger.warning("mark_failed called without trip id")
            return
        await asyncio.to_thread(self.mark_failed, trip_id, reason)
        await self.publish_event({"type":"trip_cancelled_event", "trip_id": trip_id, "reason": reason})

    async def _action_mark_failed_text(self, payload: dict):
        trip_id = self.current_trip_id_getter()
        text = payload.get("text", "").strip()
        if not text:
            await self.tts_say("Please explain the reason.")
            return
        if not trip_id:
            logger.warning("mark_failed called without trip id")
            return
        await asyncio.to_thread(self.mark_failed, trip_id, text)
        await self.publish_event({"type":"trip_cancelled_event", "trip_id": trip_id, "reason": text})

    async def _action_reset(self, payload: dict):
        self._seen_event_ids.clear()
        self.state = State.IDLE
        await self.tts_say("State reset.")
