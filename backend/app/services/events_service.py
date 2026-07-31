"""The middleman: routers ask me; I compose the store and the scorer."""
from functools import lru_cache

from app.config import get_settings
from app.db.mock_store import MockStore
from app.models.domain import CircuitLeg, Friend, FriendRsvp
from app.services.scoring_service import ScoringService
from app.db.dynamo_store import DynamoStore

class EventsService:
    def __init__(self, store, scorer: ScoringService):
        self.store = store
        self.scorer = scorer
        self.recompute()          # a service is born ready: the board exists from breath one

    # reads — thin pass-throughs on purpose
    def get_event(self, event_id): return self.store.get_event(event_id)
    def list_events(self, **kw): return self.store.list_events(**kw)
    def get_updates(self, event_id, start=None, end=None):
        return self.store.get_updates(event_id, start, end)
    def events_for_artist(self, artist_id): return self.store.events_for_artist(artist_id)
    def get_favorites(self): return self.store.get_favorites()
    def get_friends(self): return self.store.get_friends()
    def rsvps_for_event(self, event_id): return self.store.rsvps_for_event(event_id)
    def get_circuit(self): return self.store.get_circuit()

    # the brain
    def recommendations(self): return self.scorer.recommend_all()
    def score_one(self, event_id):
        ev = self.store.get_event(event_id)
        return self.scorer.score_event(ev) if ev else None

    # writes
    def add_leg(self, leg: CircuitLeg) -> bool: return self.store.add_leg(leg)
    def remove_leg(self, event_id: str) -> bool: return self.store.remove_leg(event_id)
    def add_friend(self, friend: Friend) -> None: self.store.add_friend(friend)
    def add_rsvp(self, rsvp: FriendRsvp) -> None: self.store.add_rsvp(rsvp)

    def recompute(self):
        self.store.write_recommendations(self.scorer.recommend_all())

    def recommendations(self):
        return self.store.read_recommendations()

    def add_leg(self, leg):
        ok = self.store.add_leg(leg)
        if ok: self.recompute()
        return ok

    def remove_leg(self, event_id):
        ok = self.store.remove_leg(event_id)
        if ok: self.recompute()
        return ok

    def add_rsvp(self, rsvp):
        self.store.add_rsvp(rsvp)
        self.recompute()


@lru_cache
def get_events_service() -> EventsService:
    cfg = get_settings()
    store = (DynamoStore(cfg.dynamodb_endpoint) if cfg.store_backend == "dynamo"
             else MockStore())
    svc = EventsService(store, ScoringService(store, cfg))
    svc.recompute()
    return svc