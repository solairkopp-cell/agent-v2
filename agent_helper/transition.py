from dataclasses import dataclass
from typing import Callable, Awaitable, Optional, Any

Guard = Callable[[dict], bool]
Action = Callable[[dict], Awaitable[None]]

@dataclass(frozen=True)
class Transition:
    source: Any
    event: Any
    target: Any
    guard: Optional[Guard] = None
    action: Optional[Action] = None
