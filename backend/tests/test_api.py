"""Day 1 referee: pins the API's behavior so tomorrow's storage swap has a judge."""
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db.mock_store import MockStore
from app.main import app
from app.services.events_service import EventsService, get_events_service
from app.services.scoring_service import ScoringService


@pytest.fixture()
def client():
    """A fresh app with a fresh store for every single test."""
    store = MockStore()
    svc = EventsService(store, ScoringService(store, get_settings()))
    app.dependency_overrides[get_events_service] = lambda: svc
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---- reads ----

def test_list_events_paginates(client):
    r = client.get("/api/v1/events?limit=5")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 5
    assert body["next_page_token"] is not None

def test_filter_by_kind(client):
    r = client.get("/api/v1/events?kind=festival&limit=50")
    assert all(e["kind"] == "festival" for e in r.json()["items"])

def test_unknown_event_is_enveloped_404(client):
    r = client.get("/api/v1/events/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == 404

def test_bad_limit_is_422(client):
    assert client.get("/api/v1/events?limit=-5").status_code == 422


# ---- writes ----

def test_add_leg_roundtrip_and_duplicate_409(client):
    ev_id = client.get("/api/v1/events?limit=1").json()["items"][0]["id"]
    r = client.post("/api/v1/circuit/legs", json={"event_id": ev_id})
    assert r.status_code == 201
    assert any(l["event_id"] == ev_id
               for l in client.get("/api/v1/circuit").json()["legs"])
    assert client.post("/api/v1/circuit/legs", json={"event_id": ev_id}).status_code == 409

def test_rsvp_write_and_read(client):
    ev_id = client.get("/api/v1/events?limit=1").json()["items"][0]["id"]
    r = client.post(f"/api/v1/events/{ev_id}/rsvps",
                    json={"friend_id": "f0", "status": "going"})
    assert r.status_code == 201
    rsvps = client.get(f"/api/v1/events/{ev_id}/rsvps").json()["items"]
    assert any(x["friend_id"] == "f0" and x["status"] == "going" for x in rsvps)


# ---- the two tests that guard the product's brain ----

def test_scoring_contract(client):
    recs = client.get("/api/v1/recommendations?limit=10").json()["items"]
    assert recs, "expected recommendations"
    for rec in recs:
        total = sum(f["contribution"] for f in rec["factors"])
        assert abs(total - rec["score"]) < 0.05, "factors must sum to the score"
        assert all(f["evidence"].strip() for f in rec["factors"]), "every factor explains itself"

def test_novelty_decay_dilutes_overlaps(client):
    recs = client.get("/api/v1/recommendations?limit=200").json()["items"]
    events = {r["event_id"]: client.get(f"/api/v1/events/{r['event_id']}").json()
              for r in recs[:30]}
    favs = None  # find an overlapping pair on favorites via evidence instead
    def lineup_contrib(rec):
        return next(f for f in rec["factors"] if f["name"] == "lineup_value")["contribution"]
    # add the top event, then assert at least one other event's lineup factor dropped
    top = recs[0]
    before = {r["event_id"]: lineup_contrib(r) for r in recs[1:30]}
    client.post("/api/v1/circuit/legs", json={"event_id": top["event_id"]})
    after_recs = client.get("/api/v1/recommendations?limit=200").json()["items"]
    after = {r["event_id"]: lineup_contrib(r) for r in after_recs if r["event_id"] in before}
    dropped = [eid for eid in before if after.get(eid, before[eid]) < before[eid] - 1e-6]
    assert dropped, "adding a leg should gently dilute at least one overlapping lineup"