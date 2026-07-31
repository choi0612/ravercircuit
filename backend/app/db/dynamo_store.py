"""Same face as MockStore; every method is a real DynamoDB call, per the design doc."""
from datetime import datetime
from decimal import Decimal
import json

import boto3
from boto3.dynamodb.conditions import Key

from app.models.domain import (
    Artist, CircuitLeg, Event, EventUpdate, Favorite, Friend, FriendRsvp, Recommendation,
)

TABLE = "ravercircuit"
REGIONS = ["west", "mountain", "central", "east", "other"]

def _dec(obj):
    """floats -> Decimal, DynamoDB's required number type."""
    return json.loads(json.dumps(obj, default=str), parse_float=Decimal)


class DynamoStore:
    def __init__(self, endpoint: str | None):
        kw = (dict(endpoint_url=endpoint, region_name="us-west-2",
                   aws_access_key_id="local", aws_secret_access_key="local")
              if endpoint else {})
        self.table = boto3.resource("dynamodb", **kw).Table(TABLE)

    # ---- events ----
    def get_event(self, event_id: str) -> Event | None:
        # one grab of the drawer: META + lineup slots arrive together (Q1)
        items = self.table.query(
            KeyConditionExpression=Key("PK").eq(f"EVENT#{event_id}")
        )["Items"]
        meta = next((i for i in items if i["SK"] == "META"), None)
        if meta is None:
            return None
        lineup = [{"artist_id": i["SK"].split("#")[1], "billing": int(i["billing"])}
                  for i in items if i["entity"] == "lineup_slot"]
        return Event(**{**meta, "lineup": lineup})

    def get_artist(self, artist_id: str) -> Artist | None:
        r = self.table.get_item(Key={"PK": f"ARTIST#{artist_id}", "SK": "META"})
        return Artist(**r["Item"]) if "Item" in r else None

    def all_events(self) -> list[Event]:
        # the scorer's batch walk: one GSI1 query per region — bounded, no Scan (Q3's index reused)
        evs = []
        for region in REGIONS:
            for i in self.table.query(
                IndexName="GSI1",
                KeyConditionExpression=Key("GSI1PK").eq(f"REGION#{region}"),
            )["Items"]:
                evs.append(self.get_event(i["id"]))
        return evs

    def list_events(self, kind=None, city=None, month=None, limit=25, page_token=None):
        evs = sorted(self.all_events(), key=lambda e: e.start_date)
        if kind:  evs = [e for e in evs if e.kind == kind]
        if city:  evs = [e for e in evs if e.city.lower() == city.lower()]
        if month: evs = [e for e in evs if e.start_date.month == month]
        start = int(page_token) if page_token else 0
        page = evs[start:start + limit]
        return page, (str(start + limit) if start + limit < len(evs) else None)

    def events_for_artist(self, artist_id: str) -> list[Event]:
        # the inverted index earning its keep (Q6): date-ordered by the SK itself
        hits = self.table.query(
            IndexName="GSI2",
            KeyConditionExpression=Key("GSI2PK").eq(f"ARTIST#{artist_id}"),
        )["Items"]
        return [self.get_event(h["GSI2SK"].split("#EVENT#")[1]) for h in hits]

    # ---- updates (Q2): SK slice, newest first ----
    def get_updates(self, event_id, start=None, end=None) -> list[EventUpdate]:
        cond = Key("PK").eq(f"EVENT#{event_id}")
        lo = f"UPD#{start.isoformat()}" if start else "UPD#"
        hi = f"UPD#{end.isoformat()}~" if end else "UPD#~"   # '~' sorts after digits: open end
        cond = cond & Key("SK").between(lo, hi)
        items = self.table.query(KeyConditionExpression=cond,
                                 ScanIndexForward=False)["Items"]
        return [EventUpdate(**i) for i in items]

    # ---- USER#me shelves (Q5, Q7, Q8) ----
    def _user_shelf(self, prefix: str):
        return self.table.query(
            KeyConditionExpression=Key("PK").eq("USER#me") & Key("SK").begins_with(prefix)
        )["Items"]

    def get_favorites(self):  return [Favorite(**i) for i in self._user_shelf("FAV#")]
    def get_friends(self):    return [Friend(**i) for i in self._user_shelf("FRIEND#")]

    def get_circuit(self) -> list[CircuitLeg]:
        return [CircuitLeg(**i) for i in self._user_shelf("LEG#")]   # date-sorted by SK design

    def add_leg(self, leg: CircuitLeg) -> bool:
        ev = self.get_event(leg.event_id)
        sk = f"LEG#{ev.start_date}#{leg.event_id}"
        if any(l.event_id == leg.event_id for l in self.get_circuit()):
            return False
        self.table.put_item(Item=_dec({"PK": "USER#me", "SK": sk, "entity": "leg",
                                       **leg.model_dump(mode="json")}))
        return True

    def remove_leg(self, event_id: str) -> bool:
        target = next((i for i in self._user_shelf("LEG#")
                       if i["event_id"] == event_id), None)
        if not target:
            return False
        self.table.delete_item(Key={"PK": "USER#me", "SK": target["SK"]})
        return True

    def add_friend(self, friend: Friend) -> None:
        self.table.put_item(Item=_dec({"PK": "USER#me", "SK": f"FRIEND#{friend.id}",
                                       "entity": "friend", **friend.model_dump()}))

    # ---- RSVPs (Q9): same address = automatic replace ----
    def rsvps_for_event(self, event_id: str):
        items = self.table.query(
            KeyConditionExpression=Key("PK").eq(f"EVENT#{event_id}") & Key("SK").begins_with("RSVP#")
        )["Items"]
        return [FriendRsvp(**i) for i in items]

    def add_rsvp(self, rsvp: FriendRsvp) -> None:
        # PK/SK is friend-per-event -> a second write to the same address overwrites: dedupe for free
        self.table.put_item(Item=_dec({"PK": f"EVENT#{rsvp.event_id}",
                                       "SK": f"RSVP#{rsvp.friend_id}",
                                       "entity": "rsvp", **rsvp.model_dump()}))

    # ---- materialized recommendations (Q4 + Q10) ----
    def write_recommendations(self, recs: list[Recommendation]) -> None:
        old = self._user_shelf("REC#")
        with self.table.batch_writer() as bw:
            for i in old:
                bw.delete_item(Key={"PK": "USER#me", "SK": i["SK"]})
            for r in recs:
                inv = f"{int(round((100 - r.score) * 10)):04d}"     # 91.3 -> "0087"; zero-padded text-sort
                bw.put_item(Item=_dec({"PK": "USER#me", "SK": f"REC#{inv}#{r.event_id}",
                                       "entity": "rec", **r.model_dump()}))

    def read_recommendations(self, limit: int = 200) -> list[Recommendation]:
        items = self.table.query(
            KeyConditionExpression=Key("PK").eq("USER#me") & Key("SK").begins_with("REC#"),
            Limit=limit,
        )["Items"]   # ascending SK = best first, by construction
        return [Recommendation(**i) for i in items]