"""Invent a plausible fake scene and write it to data/seed.json."""
import json
import random
from datetime import date, datetime, timedelta
from pathlib import Path


# import our contracts so everything we invent gets validated as we build it
import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))
from app.models.domain import (
    Artist, Event, EventUpdate, Favorite, Friend, FriendRsvp, Genre, LineupSlot,
)

rng = random.Random(42)  # fixed seed = same "random" scene every run

# ---- the map: home is LA; some cities are drivable, some need a flight ----
CITIES = [
    {"name": "Los Angeles",    "lat": 34.05, "lon": -118.24},
    {"name": "San Bernardino", "lat": 34.11, "lon": -117.29},
    {"name": "San Diego",      "lat": 32.72, "lon": -117.16},
    {"name": "Las Vegas",      "lat": 36.17, "lon": -115.14},
    {"name": "San Francisco",  "lat": 37.77, "lon": -122.42},
    {"name": "Phoenix",        "lat": 33.45, "lon": -112.07},
    {"name": "Denver",         "lat": 39.74, "lon": -104.99},
    {"name": "Chicago",        "lat": 41.88, "lon": -87.63},
    {"name": "Miami",          "lat": 25.76, "lon": -80.19},
    {"name": "New York",       "lat": 40.71, "lon": -74.01},
]

GENRES = [g.value for g in Genre]

# ---- invent ~200 artists with fake two-part names ----
FIRST = ["Neon", "Vex", "Kyra", "Solstice", "Drift", "Nova", "Echo", "Pulse",
         "Riot", "Lumen", "Onyx", "Zephyr", "Mira", "Static", "Ember", "Volt"]
SECOND = ["wave", "krow", "lyne", "fall", "byte", "haze", "storm", "loop",
          "shade", "flare", "run", "core", "dusk", "field", "spark", "tide"]

artists = []
for i in range(200):
    name = rng.choice(FIRST) + rng.choice(SECOND) + (str(i % 10) if i >= 160 else "")
    genre = rng.choice(GENRES)
    # a third of artists dabble in a second, neighboring genre
    roll = rng.random()
    if roll < 0.55:
        genres = [genre]                                        # specialist
    elif roll < 0.90:
        genres = [genre, rng.choice(GENRES)]                    # dual-genre
    else:
        genres = [genre] + rng.sample(GENRES, 2)                # genre-hopper, up to 3
    artists.append(Artist(id=f"a{i:03d}", name=name.title(), genres=list(set(genres))))

# popularity tier per artist: 1 = headliner-grade, 3 = undercard-grade
popularity = {a.id: rng.choices([1, 2, 3], weights=[15, 35, 50])[0] for a in artists}

def pick_lineup(size: int, flavor: str) -> list[LineupSlot]:
    """Choose artists for one event, favoring the event's genre flavor."""
    on_flavor = [a for a in artists if flavor in a.genres]
    pool = list({a.id: a for a in on_flavor + rng.sample(artists, 30)}.values())
    chosen = rng.sample(pool, min(size, len(pool)))
    slots = []
    for a in chosen:
        base = popularity[a.id]                          # popular artists bill higher
        billing = max(1, min(3, base + rng.choice([-1, 0, 0])))
        slots.append(LineupSlot(artist_id=a.id, billing=billing))
    return slots

# ---- invent the year of events ----
events, updates = [], []
YEAR = 2026
upd_count = 0

def add_updates(ev: Event, n_price_steps: int):
    """Give an event a little history: price climbing over time, maybe a sellout scare."""
    global upd_count
    price = ev.current_price * 0.7                       # tickets started cheaper
    when = datetime(YEAR, 1, 5) + timedelta(days=rng.randint(0, 60))
    for _ in range(n_price_steps):
        new_price = round(price * rng.uniform(1.10, 1.25), 0)
        updates.append(EventUpdate(
            id=f"u{upd_count:04d}", event_id=ev.id, type="price_tier_change",
            occurred_at=when, detail=f"${price:.0f} -> ${new_price:.0f}"))
        upd_count += 1
        price, when = new_price, when + timedelta(days=rng.randint(20, 45))
    if rng.random() < 0.15:
        updates.append(EventUpdate(
            id=f"u{upd_count:04d}", event_id=ev.id, type="sellout_warning",
            occurred_at=when, detail="GA nearly gone"))
        upd_count += 1

# 40 festivals, clustered toward summer
for i in range(40):
    city = rng.choice(CITIES)
    month = rng.choices(range(1, 13), weights=[2,2,4,6,8,10,10,10,8,6,3,2])[0]
    start = date(YEAR, month, rng.randint(1, 25))
    flavor = rng.choice(GENRES)
    ev = Event(
        id=f"e{i:03d}",
        name=f"{rng.choice(FIRST)} {rng.choice(['Bloom','Grounds','Lands','Canyon','Harbor'])}",
        kind="festival", city=city["name"], lat=city["lat"], lon=city["lon"],
        start_date=start, end_date=start + timedelta(days=rng.choice([1, 2])),
        current_price=float(rng.randint(180, 450)),
        production=rng.choice([3, 4, 4, 5]),
        activities=rng.sample(["art cars", "carnival rides", "camping", "silent disco",
                               "fireworks", "water station art"], k=rng.randint(1, 3)),
        lineup=pick_lineup(rng.randint(20, 60), flavor),
    )
    events.append(ev)
    add_updates(ev, n_price_steps=rng.randint(1, 3))

# 150 club/warehouse shows, spread across the year
for i in range(150):
    city = rng.choice(CITIES[:6])                        # smaller shows skew regional
    start = date(YEAR, rng.randint(1, 12), rng.randint(1, 28))
    flavor = rng.choice(GENRES)
    kind = rng.choice(["club", "club", "warehouse"])
    ev = Event(
        id=f"e{i + 40:03d}",
        name=f"{rng.choice(FIRST)}{rng.choice(SECOND)} presents",
        kind=kind, city=city["name"], lat=city["lat"], lon=city["lon"],
        start_date=start, end_date=start,
        current_price=float(rng.randint(25, 85)),
        production=rng.choice([1, 2, 2, 3]),
        lineup=pick_lineup(rng.randint(1, 5), flavor),
    )
    events.append(ev)
    if rng.random() < 0.5:                               # half the shows have some history
        add_updates(ev, n_price_steps=1)

# ---- your taste: ~25 favorites, skewed to two genres you "love" ----
loved = rng.sample(GENRES, 2)
lovers = [a for a in artists if any(g in loved for g in a.genres)]
favs = rng.sample(lovers, 20) + rng.sample(artists, 5)
favorites = [Favorite(artist_id=a.id,
                      affinity=round(rng.uniform(0.75, 1.0) if a in favs[:5]
                                     else rng.uniform(0.3, 0.9), 2))
             for a in favs]

# ---- the crew: 6 friends, each RSVPed to a handful of events ----
friends = [Friend(id=f"f{i}", name=n) for i, n in
           enumerate(["Alex", "Sam", "Jordan", "Maya", "Chris", "Dev"])]
rsvps = []
for fr in friends:
    for ev in rng.sample(events, rng.randint(3, 8)):
        rsvps.append(FriendRsvp(friend_id=fr.id, event_id=ev.id,
                                status=rng.choice(["going", "going", "interested"])))

# ---- write everything to one file, dates converted to plain text ----
out = Path(__file__).resolve().parents[1] / "data"
out.mkdir(exist_ok=True)
seed = {
    "artists":   [a.model_dump(mode="json") for a in artists],
    "events":    [e.model_dump(mode="json") for e in events],
    "updates":   [u.model_dump(mode="json") for u in updates],
    "favorites": [f.model_dump(mode="json") for f in favorites],
    "friends":   [f.model_dump(mode="json") for f in friends],
    "rsvps":     [r.model_dump(mode="json") for r in rsvps],
}
(out / "seed.json").write_text(json.dumps(seed, indent=2))
print("wrote data/seed.json:",
      {k: len(v) for k, v in seed.items()})