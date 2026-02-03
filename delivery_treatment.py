"""
Delivery Treatment Finite State Machine
Rigorous, deterministic, and scalable implementation
"""

import logging
from typing import Callable, Optional
from datetime import datetime

from agent_helper.core import StateMachine
from agent_helper.enums import Event, TreatmentState
from agent_helper.transition import Transition

from delivery import (
    DeliveryContext,
    DeliveryRules,
    DeliveryState,
    FailureReason,
)

logger = logging.getLogger("fsm.delivery")


# ==========================================================
# ACTIONS
# ==========================================================

class TreatmentActions:
    """
    Side-effect actions executed during FSM transitions.
    No state decision logic here. Only effects.
    """

    def __init__(
        self,
        tts_say: Callable,
        publish_event: Callable,
    ):
        self.tts_say = tts_say
        self.publish_event = publish_event

    async def ask_completion(self, ctx: dict):
        await self.tts_say("You have arrived. Is the delivery completed? Please answer yes or no.")

    async def ask_reason(self, ctx: dict):
        await self.tts_say(
            "Okay. Please choose a reason by number. "
            "1. Recipient absent. "
            "2. No safe place. "
            "3. Access not possible. "
            "4. Address not found. "
            "5. Recipient refused. "
            "6. Other reason."
        )

    async def ask_reason_detail(self, ctx: dict):
        await self.tts_say("Please describe the reason for non-delivery.")

    async def ask_photo(self, ctx: dict):
        delivery: DeliveryContext = ctx["delivery"]

        await self.tts_say("Please take a photo of the package.")

        await self.publish_event({
            "type": "ask_photo_event",
            "delivery_id": delivery.delivery_id,
            "address": delivery.address,
            "timestamp": datetime.now().isoformat(),
        })

    async def mark_completed(self, ctx: dict):
        delivery: DeliveryContext = ctx["delivery"]
        delivery.state = DeliveryState.COMPLETED
        delivery.completed_at = datetime.now()
        await self.publish_event({
            "type": "delivery_confirmed",
            "delivery_id": delivery.delivery_id,
            "address": delivery.address,
            "timestamp": datetime.now().isoformat(),
        })

        fn = ctx.get("mark_completed")
        if fn:
            fn(delivery.delivery_id)

    async def mark_completed_with_photo(self, ctx: dict):
        delivery: DeliveryContext = ctx["delivery"]
        delivery.state = DeliveryState.COMPLETED_WITH_PHOTO
        delivery.completed_at = datetime.now()

        fn = ctx.get("mark_completed")
        await self.publish_event({
            "type": "delivery_confirmed",
            "delivery_id": delivery.delivery_id,
            "address": delivery.address,
            "timestamp": datetime.now().isoformat(),
        })
        if fn:
            fn(delivery.delivery_id)

    async def mark_failed(self, ctx: dict):
        delivery: DeliveryContext = ctx["delivery"]
        delivery.state = DeliveryState.FAILED

        reason_text = delivery.get_failure_description()

        fn = ctx.get("mark_failed")
        await self.publish_event({
            "type": "delivery_confirmed",
            "delivery_id": delivery.delivery_id,
            "address": delivery.address,
            "timestamp": datetime.now().isoformat(),
        })
        if fn:
            fn(delivery.delivery_id, reason_text)

    async def finalize_treatment(self, ctx: dict):
        delivery: DeliveryContext = ctx["delivery"]

        await self.publish_event({
            "type": "delivery_treatment_finished",
            "delivery_id": delivery.delivery_id,
            "success": delivery.state in (
                DeliveryState.COMPLETED,
                DeliveryState.COMPLETED_WITH_PHOTO,
            ),
            "final_state": delivery.state.name,
            "timestamp": datetime.now().isoformat(),
        })

        logger.info(
            "Delivery treatment finalized",
            extra={
                "delivery_id": delivery.delivery_id,
                "state": delivery.state.name,
            },
        )


# ==========================================================
# GUARDS
# ==========================================================

class TreatmentGuards:
    """Pure business rules. No side effects."""

    @staticmethod
    def requires_detail(ctx: dict) -> bool:
        delivery: DeliveryContext = ctx["delivery"]
        return DeliveryRules.requires_reason_detail(
            delivery.failure_reason
        )

    @staticmethod
    def requires_photo(ctx: dict) -> bool:
        delivery: DeliveryContext = ctx["delivery"]
        return DeliveryRules.requires_photo(
            delivery.failure_reason
        )

    @staticmethod
    def immediate_failure(ctx: dict) -> bool:
        delivery: DeliveryContext = ctx["delivery"]
        return (
            not DeliveryRules.requires_photo(delivery.failure_reason)
            and not DeliveryRules.requires_reason_detail(delivery.failure_reason)
        )


# ==========================================================
# TRANSITIONS
# ==========================================================

def build_treatment_transitions(
    actions: TreatmentActions,
) -> list[Transition]:

    guards = TreatmentGuards()

    return [
        # ----- ASK DELIVERY COMPLETION -----
        Transition(
            TreatmentState.ASK_DELIVERY_COMPLETION,
            Event.CONFIRM_YES,
            TreatmentState.FINALIZE,
            action=actions.mark_completed,
        ),
        Transition(
            TreatmentState.ASK_DELIVERY_COMPLETION,
            Event.CONFIRM_NO,
            TreatmentState.ASK_NON_DELIVERY_REASON,
            action=actions.ask_reason,
        ),

        # ----- ASK NON DELIVERY REASON -----
        Transition(
            TreatmentState.ASK_NON_DELIVERY_REASON,
            Event.REASON_NUMBER,
            TreatmentState.ASK_REASON_DETAIL,
            guard=guards.requires_detail,
            action=actions.ask_reason_detail,
        ),
        Transition(
            TreatmentState.ASK_NON_DELIVERY_REASON,
            Event.REASON_NUMBER,
            TreatmentState.ASK_PHOTO,
            guard=guards.requires_photo,
            action=actions.ask_photo,
        ),
        Transition(
            TreatmentState.ASK_NON_DELIVERY_REASON,
            Event.REASON_NUMBER,
            TreatmentState.FINALIZE,
            guard=guards.immediate_failure,
            action=actions.mark_failed,
        ),

        # ----- ASK REASON DETAIL -----
        Transition(
            TreatmentState.ASK_REASON_DETAIL,
            Event.REASON_TEXT,
            TreatmentState.ASK_PHOTO,
            guard=guards.requires_photo,
            action=actions.ask_photo,
        ),
        Transition(
            TreatmentState.ASK_REASON_DETAIL,
            Event.REASON_TEXT,
            TreatmentState.FINALIZE,
            action=actions.mark_failed,
        ),

        # ----- ASK PHOTO -----
        Transition(
            TreatmentState.ASK_PHOTO,
            Event.PHOTO_TAKEN,
            TreatmentState.FINALIZE,
            action=actions.mark_completed_with_photo,
        ),
        Transition(
            TreatmentState.ASK_PHOTO,
            Event.PHOTO_NOT_TAKEN,
            TreatmentState.FINALIZE,
            action=actions.mark_failed,
        ),
    ]


# ==========================================================
# FSM WRAPPER
# ==========================================================

class DeliveryTreatmentFSM:
    """
    High-level orchestrator.
    Holds context. FSM handles flow. Agent stays decoupled.
    """

    def __init__(
        self,
        tts_say: Callable,
        publish_event: Callable,
        mark_completed: Callable,
        mark_failed: Callable,
    ):
        self.actions = TreatmentActions(
            tts_say=tts_say,
            publish_event=publish_event,
        )

        self.fsm = StateMachine(
            name="DeliveryTreatmentFSM",
            initial_state=TreatmentState.ASK_DELIVERY_COMPLETION,
            transitions=build_treatment_transitions(self.actions),
            on_enter={
                TreatmentState.ASK_DELIVERY_COMPLETION: self.actions.ask_completion,
                TreatmentState.FINALIZE: self.actions.finalize_treatment,
            },
        )

        self.mark_completed = mark_completed
        self.mark_failed = mark_failed

        self.delivery: Optional[DeliveryContext] = None

    async def start_treatment(
        self,
        delivery_id: str,
        address: str = "",
    ):
        self.delivery = DeliveryContext(
            delivery_id=delivery_id,
            address=address,
        )
        self.fsm.reset(TreatmentState.ASK_DELIVERY_COMPLETION)
        await self.actions.ask_completion({"delivery": self.delivery})

    async def handle_event(
        self,
        event: Event,
        data: dict | None = None,
        event_id: str | None = None,
    ):
        if not self.delivery:
            logger.warning("Treatment not started")
            return

        data = data or {}
        self._update_context(event, data)

        ctx = {
            "delivery": self.delivery,
            "mark_completed": self.mark_completed,
            "mark_failed": self.mark_failed,
        }

        await self.fsm.handle_event(event, ctx, event_id=event_id)

    def _update_context(self, event: Event, data: dict):
        current_state = self.fsm.state

        if event == Event.REASON_NUMBER and current_state == TreatmentState.ASK_NON_DELIVERY_REASON:
            self.delivery.failure_reason = FailureReason.from_number(
                data.get("number")
            )

        elif event == Event.REASON_TEXT and current_state == TreatmentState.ASK_REASON_DETAIL:
            text = data.get("text", "").strip()
            if text:
                self.delivery.failure_reason_text = text
                if self.delivery.failure_reason is None:
                    self.delivery.failure_reason = FailureReason.OTHER

        elif event == Event.PHOTO_TAKEN and current_state == TreatmentState.ASK_PHOTO:
            self.delivery.photo_taken = True

    async def reprompt(self) -> None:
        """Repeat the current question to keep the flow deterministic."""
        if not self.delivery:
            return

        ctx = {
            "delivery": self.delivery,
            "mark_completed": self.mark_completed,
            "mark_failed": self.mark_failed,
        }

        if self.fsm.state == TreatmentState.ASK_DELIVERY_COMPLETION:
            await self.actions.ask_completion(ctx)
        elif self.fsm.state == TreatmentState.ASK_NON_DELIVERY_REASON:
            await self.actions.ask_reason(ctx)
        elif self.fsm.state == TreatmentState.ASK_REASON_DETAIL:
            await self.actions.ask_reason_detail(ctx)
        elif self.fsm.state == TreatmentState.ASK_PHOTO:
            # Don't re-publish ask_photo_event on every reprompt; just remind the driver.
            await self.actions.tts_say("Please take a photo of the package in the app.")

    def is_active(self) -> bool:
        return (
            self.delivery is not None
            and self.fsm.state != TreatmentState.FINALIZE
        )

    def get_state(self) -> TreatmentState:
        return self.fsm.state

    def cleanup(self):
        self.delivery = None
