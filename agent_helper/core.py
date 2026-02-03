import asyncio
import logging
from typing import Any, Dict, Iterable, Set, Optional

from agent_helper.transition import Transition

logger = logging.getLogger("state_machine")


class InvalidTransition(Exception):
    pass


class StateMachine:
    def __init__(
        self,
        *,
        initial_state: Any,
        transitions: Iterable[Transition],
        name: str = "FSM",
        on_enter: Optional[dict[Any, callable]] = None,
    ):
        self._initial_state = initial_state
        self._state = initial_state
        self._name = name
        self._on_enter = on_enter or {}

        self._transitions: Dict[tuple, list[Transition]] = {}
        self._processed_events: Set[str] = set()
        self._lock = asyncio.Lock()

        for t in transitions:
            key = (t.source, t.event)
            self._transitions.setdefault(key, []).append(t)

        logger.info("[%s] Initialized in state %s", self._name, self._state)

    @property
    def state(self) -> Any:
        return self._state

    async def handle_event(
        self,
        event: Any,
        payload: Dict | None = None,
        *,
        event_id: str | None = None,
    ) -> None:
        async with self._lock:
            if event_id:
                if event_id in self._processed_events:
                    logger.debug("[%s] Duplicate event ignored: %s", self._name, event_id)
                    return
                self._processed_events.add(event_id)

            payload = payload or {}
            payload["state"] = self._state
            payload["event"] = event

            key = (self._state, event)
            candidates = self._transitions.get(key)

            if not candidates:
                logger.warning(
                    "[%s] Ignored event %s in state %s",
                    self._name, event, self._state
                )
                return

            transition = self._select_transition(candidates, payload)

            if not transition:
                logger.warning(
                    "[%s] Guards rejected event %s in state %s",
                    self._name, event, self._state
                )
                return

            logger.info(
                "[%s] %s --(%s)--> %s",
                self._name,
                self._state,
                event,
                transition.target,
            )

            if transition.action:
                await transition.action(payload)

            self._state = transition.target

            on_enter = self._on_enter.get(self._state)
            if on_enter:
                await on_enter(payload)

    def _select_transition(self, transitions: list[Transition], payload: Dict):
        for t in transitions:
            if t.guard is None or t.guard(payload):
                return t
        return None

    def reset(self, state: Any | None = None):
        self._state = state or self._initial_state
        self._processed_events.clear()
        logger.info("[%s] Reset to state %s", self._name, self._state)
