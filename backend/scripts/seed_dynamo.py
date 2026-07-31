"""Load data/seed.json into the ravercircuit table, per the design doc."""
import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from scripts.create_table import TABLE, resource

REGION_OF = {
    "Los Angeles": "west", "San Bernardino": "west", "San Diego": "west",
    "Las Vegas": "west", "San Francisco": "west", "Phoenix": "west",
    "Denver": "mountain", "Chicago": "central", "Miami": "east", "New York": "east",
}

def dec(obj):
    """Recursively convert floats to Decimal (DynamoDB requirement)."""
    return json.loads(json.dumps(obj), parse_float=Decimal)

def main():
    raw = json.loads((Path(__file__).resolve().parents[1] / "data" / "seed.json").read_text())
    table = resource().Table(TABLE)
    n = 0
    with table.batch_writer() as bw:
        for a in raw["artists"]:
            bw.put_item(Item=dec({"PK": f"ARTIST#{a['id']}", "SK": "META",
                                  "entity": "artist", **a}))
            n += 1
        for e in raw["events"]:
            region = REGION_OF.get(e["city"], "other")
            meta = {k: v for k, v in e.items() if k != "lineup"}
            bw.put_item(Item=dec({
                "PK": f"EVENT#{e['id']}", "SK": "META", "entity": "event",
                "GSI1PK": f"REGION#{region}",
                "GSI1SK": f"DATE#{e['start_date']}#EVENT#{e['id']}", **meta}))
            n += 1
            for slot in e["lineup"]:
                bw.put_item(Item=dec({
                    "PK": f"EVENT#{e['id']}", "SK": f"ARTIST#{slot['artist_id']}",
                    "entity": "lineup_slot", "billing": slot["billing"],
                    "GSI2PK": f"ARTIST#{slot['artist_id']}",
                    "GSI2SK": f"DATE#{e['start_date']}#EVENT#{e['id']}"}))
                n += 1
        for u in raw["updates"]:
            bw.put_item(Item=dec({"PK": f"EVENT#{u['event_id']}",
                                  "SK": f"UPD#{u['occurred_at']}#{u['id']}",
                                  "entity": "update", **u}))
            n += 1
        for f in raw["favorites"]:
            bw.put_item(Item=dec({"PK": "USER#me", "SK": f"FAV#{f['artist_id']}",
                                  "entity": "favorite", **f}))
            n += 1
        for fr in raw["friends"]:
            bw.put_item(Item=dec({"PK": "USER#me", "SK": f"FRIEND#{fr['id']}",
                                  "entity": "friend", **fr}))
            n += 1
        for r in raw["rsvps"]:
            bw.put_item(Item=dec({"PK": f"EVENT#{r['event_id']}", "SK": f"RSVP#{r['friend_id']}",
                                  "entity": "rsvp", **r}))
            n += 1
    print(f"seeded {n} items into '{TABLE}'")

if __name__ == "__main__":
    main()