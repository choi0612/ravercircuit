"""In-memory store backed by data/seed.json. Same question-shapes as tomorrow's DynamoDB."""
import json
from datetime import date, datetime
from pathlib import Path

from app.models.domain import (
    Artist, CircuitLeg, Event, EventUpdate, Favorite, Friend, FriendRsvp,
)


class MockStore:
    def __init__(self, seed_path: str | None = None):
        path = Path(seed_path) if seed_path else Path(__file__).resolve().parents[2] / "data" / "seed.json"
        raw = json.loads(path.read_text())

        # rebuild real objects from the file (validated on the way in)
        self._artists = {a["id"]: Artist(**a) for a in raw["artists"]}
        self._events = {e["id"]: Event(**e) for e in raw["events"]}
        self._updates = [EventUpdate(**u) for u in raw["updates"]]
        self._favorites = [Favorite(**f) for f in raw["favorites"]]
        self._friends = {f["id"]: Friend(**f) for f in raw["friends"]}
        self._rsvps = [FriendRsvp(**r) for r in raw["rsvps"]]
        self._legs: list[CircuitLeg] = []          # your circuit starts empty

    # ---- lookups ----
    def get_event(self, event_id: str) -> Event | None:
        return self._events.get(event_id)

    def get_artist(self, artist_id: str) -> Artist | None:
        return self._artists.get(artist_id)

    def get_favorites(self) -> list[Favorite]:
        return list(self._favorites)

    # ---- browsing with filters + pagination ----
    def list_events(self, kind: str | None = None, city: str | None = None,
                    month: int | None = None, limit: int = 25,
                    page_token: str | None = None) -> tuple[list[Event], str | None]:
        evs = sorted(self._events.values(), key=lambda e: e.start_date)
        if kind:
            evs = [e for e in evs if e.kind == kind]
        if city:
            evs = [e for e in evs if e.city.lower() == city.lower()]
        if month:
            evs = [e for e in evs if e.start_date.month == month]
        start = int(page_token) if page_token else 0
        page = evs[start:start + limit]
        next_token = str(start + limit) if start + limit < len(evs) else None
        return page, next_token

    def events_for_artist(self, artist_id: str) -> list[Event]:
        return sorted(
            [e for e in self._events.values()
             if any(s.artist_id == artist_id for s in e.lineup)],
            key=lambda e: e.start_date)

    def all_events(self) -> list[Event]:
        return list(self._events.values())

    # ---- the updates stream ----
    def get_updates(self, event_id: str, start: datetime | None = None,
                    end: datetime | None = None) -> list[EventUpdate]:
        ups = [u for u in self._updates if u.event_id == event_id]
        if start:
            ups = [u for u in ups if u.occurred_at >= start]
        if end:
            ups = [u for u in ups if u.occurred_at <= end]
        return sorted(ups, key=lambda u: u.occurred_at, reverse=True)

    # ---- your circuit (the write path) ----
    def get_circuit(self) -> list[CircuitLeg]:
        return sorted(self._legs, key=lambda l: self._events[l.event_id].start_date)

    def add_leg(self, leg: CircuitLeg) -> bool:
        """False = already in the circuit (caller decides what that means)."""
        if any(l.event_id == leg.event_id for l in self._legs):
            return False
        self._legs.append(leg)
        return True

    def remove_leg(self, event_id: str) -> bool:
        before = len(self._legs)
        self._legs = [l for l in self._legs if l.event_id != event_id]
        return len(self._legs) < before

    # ---- the crew ----
    def get_friends(self) -> list[Friend]:
        return list(self._friends.values())

    def add_friend(self, friend: Friend) -> None:
        self._friends[friend.id] = friend

    def rsvps_for_event(self, event_id: str) -> list[FriendRsvp]:
        return [r for r in self._rsvps if r.event_id == event_id]

    def add_rsvp(self, rsvp: FriendRsvp) -> None:
        # one opinion per friend per event: replace if it exists
        self._rsvps = [r for r in self._rsvps
                       if not (r.friend_id == rsvp.friend_id and r.event_id == rsvp.event_id)]
        self._rsvps.append(rsvp)