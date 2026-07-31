from datetime import date, datetime
from enum import Enum
from pydantic import BaseModel, Field


class Genre(str, Enum):
    HOUSE = "house"
    TECHNO = "techno"
    BASS = "bass"
    TRANCE = "trance"
    DNB = "dnb"
    HARDSTYLE = "hardstyle"
    DUBSTEP = "dubstep"
    MELODIC = "melodic"
    PROGRESSIVE_HOUSE = "progressive house"


class EventKind(str, Enum):
    FESTIVAL = "festival"
    CLUB = "club"
    WAREHOUSE = "warehouse"


class UpdateType(str, Enum):
    LINEUP_ADD = "lineup_add"
    PRICE_TIER_CHANGE = "price_tier_change"
    DATE_CHANGE = "date_change"
    SELLOUT_WARNING = "sellout_warning"


class LegStatus(str, Enum):
    PLANNED = "planned"
    ATTENDED = "attended"


class RsvpStatus(str, Enum):
    GOING = "going"
    INTERESTED = "interested"


class Artist(BaseModel):
    id: str
    name: str
    genres: list[Genre]


class LineupSlot(BaseModel):
    artist_id: str
    billing: int = Field(ge=1, le=3)  # 1 = headliner, 2 = support, 3 = undercard


class Event(BaseModel):
    id: str
    name: str
    kind: EventKind
    city: str
    lat: float
    lon: float
    start_date: date
    end_date: date
    current_price: float = Field(ge=0)
    production: int = Field(default=3, ge=1, le=5)  # 5 = EDC-tier, 1 = bare warehouse; 3 = unrated/neutral
    activities: list[str] = Field(default_factory=list)  # "carnival rides", "art cars", ...
    lineup: list[LineupSlot]


class EventUpdate(BaseModel):
    id: str
    event_id: str
    type: UpdateType
    occurred_at: datetime
    detail: str = ""


class Favorite(BaseModel):
    artist_id: str
    affinity: float = Field(ge=0, le=1)


class CircuitLeg(BaseModel):
    event_id: str
    status: LegStatus
    added_at: datetime


class Friend(BaseModel):
    id: str
    name: str


class FriendRsvp(BaseModel):
    friend_id: str
    event_id: str
    status: RsvpStatus


class ScoreFactor(BaseModel):
    name: str  # lineup_value | cost_efficiency | chain_bonus | crew | production_fit | weather_comfort
    weight: float
    contribution: float
    evidence: str


class Recommendation(BaseModel):
    event_id: str
    score: float = Field(ge=0, le=100)
    factors: list[ScoreFactor]