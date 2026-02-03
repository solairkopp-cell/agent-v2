from typing import Optional
from livekit.agents import function_tool, RunContext
from datetime import datetime

from data.models.trip_store import get_trip_store
from data.models.trip_state import TripState


# ========= UTILITAIRES =========

@function_tool()
async def get_current_time(context: RunContext) -> str:
    return datetime.now().strftime("It is %H:%M.")


@function_tool()
async def get_trip_count(context: RunContext) -> str:
    store = get_trip_store()
    return f"There are {store.count()} trips in the system."


@function_tool()
async def list_active_trips(context: RunContext) -> str:
    store = get_trip_store()
    trips = store.get_all()

    if not trips:
        return "There are no active trips."

    lines = []
    for trip in trips:
        lines.append(f"{trip.id} to {trip.address}")

    return "Active trips are: " + ", ".join(lines)


@function_tool()
async def list_all_trips(context: RunContext) -> str:
    store = get_trip_store()
    trips = store.get_all()

    if not trips:
        return "There are no trips recorded."

    return f"There are {len(trips)} total trips."


@function_tool()
async def get_trip_info(context: RunContext, trip_id: str) -> str:
    store = get_trip_store()
    trip = store.get(trip_id)

    if not trip:
        return f"Trip {trip_id} was not found."

    return (
        f"Trip {trip.id} is going to {trip.address}. "
        f"Current state is {trip.state.value}."
    )


# ========= GESTION D'ÉTAT =========

async def _set_trip_state(trip_id: str, new_state: TripState) -> str:
    store = get_trip_store()
    trip = store.get(trip_id)

    if not trip:
        return f"Trip {trip_id} was not found."

    trip.state = new_state
    store.update(trip)

    return f"TRIP_STATE_CHANGED::{trip_id}::{new_state.value}"


@function_tool()
async def set_trip_state_to_not_started(context: RunContext, trip_id: str) -> str:
    return await _set_trip_state(trip_id, TripState.NOT_STARTED)


@function_tool()
async def set_trip_state_to_in_progress(context: RunContext, trip_id: str) -> str:
    return await _set_trip_state(trip_id, TripState.IN_PROGRESS)


@function_tool()
async def set_trip_state_to_completed(context: RunContext, trip_id: str) -> str:
    return await _set_trip_state(trip_id, TripState.COMPLETED)


@function_tool()
async def set_trip_state_to_cancelled(context: RunContext, trip_id: str) -> str:
    return await _set_trip_state(trip_id, TripState.CANCELLED)


# ========= WORKFLOWS LIVRAISON =========

@function_tool()
async def complete_delivery(context: RunContext, trip_id: str) -> str:
    store = get_trip_store()
    trip = store.get(trip_id)

    if not trip:
        return f"Trip {trip_id} was not found."

    trip.state = TripState.COMPLETED
    store.update(trip)

    return f"DELIVERY_COMPLETED::{trip_id}"


@function_tool()
async def handle_failed_delivery(
    context: RunContext,
    trip_id: str,
    reason: Optional[str] = None
) -> str:
    store = get_trip_store()
    trip = store.get(trip_id)

    if not trip:
        return f"Trip {trip_id} was not found."

    trip.state = TripState.CANCELLED
    trip.failure_reason = reason
    store.update(trip)

    reason_text = reason or "unspecified reason"
    return f"DELIVERY_FAILED::{trip_id}::{reason_text}"


# ========= MESSAGERIE LOGIQUE (PAS RTC) =========

@function_tool()
async def send_message(context: RunContext, message: str) -> str:
    # Le LLM demande à parler → l'agent fera le say()
    return f"SAY::{message}"


@function_tool()
async def send_ask_photo_event(context: RunContext) -> str:
    return "REQUEST_PHOTO"


@function_tool()
async def send_trip_started_event(context: RunContext, trip_id: str) -> str:
    return f"EVENT_TRIP_STARTED::{trip_id}"


@function_tool()
async def send_trip_completed_event(context: RunContext, trip_id: str) -> str:
    return f"EVENT_TRIP_COMPLETED::{trip_id}"


@function_tool()
async def send_trip_cancelled_event(context: RunContext, trip_id: str) -> str:
    return f"EVENT_TRIP_CANCELLED::{trip_id}"


@function_tool()
async def send_Trip_update_event(context: RunContext, trip_id: str, state: str) -> str:
    return f"EVENT_TRIP_UPDATE::{trip_id}::{state}"
