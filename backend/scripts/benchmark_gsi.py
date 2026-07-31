"""Stopwatch showdown: Query-via-GSI2 vs Scan-with-filter on a 5,000-event table."""
import random
import sys
import time
from pathlib import Path

from boto3.dynamodb.conditions import Attr, Key

sys.path.append(str(Path(__file__).resolve().parents[1]))
from scripts.create_table import resource

BENCH = "ravercircuit_bench"
rng = random.Random(7)


def ensure_table(db):
    if BENCH in [t.name for t in db.tables.all()]:
        return db.Table(BENCH)
    t = db.create_table(
        TableName=BENCH, BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[
            {"AttributeName": "PK",     "AttributeType": "S"},
            {"AttributeName": "SK",     "AttributeType": "S"},
            {"AttributeName": "GSI2PK", "AttributeType": "S"},
            {"AttributeName": "GSI2SK", "AttributeType": "S"},
        ],
        KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"},
                   {"AttributeName": "SK", "KeyType": "RANGE"}],
        GlobalSecondaryIndexes=[{
            "IndexName": "GSI2",
            "KeySchema": [{"AttributeName": "GSI2PK", "KeyType": "HASH"},
                          {"AttributeName": "GSI2SK", "KeyType": "RANGE"}],
            "Projection": {"ProjectionType": "ALL"},
        }],
    )
    t.wait_until_exists()
    return t


def seed(t):
    if t.item_count:
        print(f"bench table already holds ~{t.item_count} items; skipping seed")
        return
    n_events, n_artists = 5000, 800
    print(f"seeding {n_events} events (~50k items — a minute or two)...")
    with t.batch_writer() as bw:
        for i in range(n_events):
            eid = f"e{i:05d}"
            day = f"2026-{rng.randint(1,12):02d}-{rng.randint(1,28):02d}"
            bw.put_item(Item={"PK": f"EVENT#{eid}", "SK": "META",
                              "entity": "event", "id": eid, "start_date": day})
            for a in rng.sample(range(n_artists), rng.randint(4, 12)):
                aid = f"a{a:04d}"
                bw.put_item(Item={"PK": f"EVENT#{eid}", "SK": f"ARTIST#{aid}",
                                  "entity": "lineup_slot",
                                  "GSI2PK": f"ARTIST#{aid}",
                                  "GSI2SK": f"DATE#{day}#EVENT#{eid}"})
    print("seeded.")


def race(t, artist="a0007"):
    # lane 1: walk to the drawer
    t0 = time.perf_counter()
    r = t.query(IndexName="GSI2",
                KeyConditionExpression=Key("GSI2PK").eq(f"ARTIST#{artist}"))
    q_ms = (time.perf_counter() - t0) * 1000
    q_found = r["Count"]

    # lane 2: read the whole building, keep the matches (paginated — Scans always are)
    t0 = time.perf_counter()
    found = examined = 0
    kw = dict(FilterExpression=Attr("GSI2PK").eq(f"ARTIST#{artist}"))
    while True:
        page = t.scan(**kw)
        found += page["Count"]
        examined += page["ScannedCount"]
        if "LastEvaluatedKey" not in page:
            break
        kw["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    s_ms = (time.perf_counter() - t0) * 1000

    print(f"\nQUERY via GSI2 : {q_found:5d} gigs in {q_ms:8.1f} ms — examined {q_found} items")
    print(f"SCAN + filter  : {found:5d} gigs in {s_ms:8.1f} ms — examined {examined} items")
    print(f"→ the scan examined {examined // max(q_found, 1):,}x more items "
          f"and ran {s_ms / max(q_ms, 0.1):,.0f}x slower here")


if __name__ == "__main__":
    db = resource()
    t = ensure_table(db)
    seed(t)
    race(t)