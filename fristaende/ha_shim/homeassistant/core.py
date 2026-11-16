from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def callback(func):
    return func


@dataclass
class Event:
    event_type: str
    data: dict = field(default_factory=dict)


@dataclass
class State:
    entity_id: str
    state: str = ""
    attributes: dict = field(default_factory=dict)


class HomeAssistant:  # typen; den riktiga värden är skolan_app.varden.Varden
    data: dict[str, Any]
