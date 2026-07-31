"""The six-factor brain: how good is this event, for you, right now."""
import math
from app.config import Settings
from app.db.mock_store import MockStore
from app.models.domain import Event, Recommendation, ScoreFactor

# comfort by month for each metro: 1.0 = perfect season, low = brutal
CLIMATE = {
    "Los Angeles":    [.7,.7,.8,.9,1,1,.9,.9,1,1,.9,.7],
    "San Bernardino": [.7,.7,.8,.9,.9,.8,.6,.6,.8,.9,.9,.7],
    "San Diego":      [.7,.8,.8,.9,1,1,1,1,1,1,.9,.8],
    "Las Vegas":      [.6,.7,.8,.9,.7,.4,.3,.3,.6,.8,.7,.6],
    "San Francisco":  [.6,.6,.7,.8,.8,.9,.9,.9,1,1,.8,.6],
    "Phoenix":        [.8,.8,.9,.8,.6,.3,.2,.2,.5,.8,.9,.8],
    "Denver":         [.4,.4,.6,.7,.8,.9,.9,.9,.9,.8,.5,.4],
    "Chicago":        [.2,.3,.5,.7,.8,.9,.9,.9,.9,.7,.5,.3],
    "Miami":          [.9,.9,.9,.8,.7,.5,.5,.4,.4,.6,.8,.9],
    "New York":       [.3,.3,.5,.7,.8,.9,.8,.8,.9,.8,.6,.4],
}

def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    """Distance between two map points, in km."""
    r = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1) * math.cos(p2) * math.sin(dl/2)**2
    return 2 * r * math.asin(math.sqrt(a))


class ScoringService:
    def __init__(self, store: MockStore, settings: Settings):
        self.store = store
        self.cfg = settings

    def recommend_all(self) -> list[Recommendation]:
        """Score every event not already in the circuit; best first."""
        in_circuit = {l.event_id for l in self.store.get_circuit()}
        recs = [self.score_event(e) for e in self.store.all_events()
                if e.id not in in_circuit]
        return sorted(recs, key=lambda r: r.score, reverse=True)

    def score_event(self, ev: Event) -> Recommendation:
        factors = [
            self._lineup_value(ev),
            self._cost_efficiency(ev),
            self._chain_bonus(ev),
            self._crew(ev),
            self._production_fit(ev),
            self._weather_comfort(ev),
        ]
        score = round(sum(f.contribution for f in factors), 1)
        return Recommendation(event_id=ev.id, score=score, factors=factors)

    # ---------- the six ingredients ----------

    def _lineup_value(self, ev: Event) -> ScoreFactor:
        favs = {f.artist_id: f.affinity for f in self.store.get_favorites()}

        # only bother counting past coverage if the novelty dial is turned up
        coverage: dict[str, int] = {}
        if self.cfg.novelty_decay > 0:
            for leg in self.store.get_circuit():
                for slot in self.store.get_event(leg.event_id).lineup:
                    if slot.artist_id in favs:
                        coverage[slot.artist_id] = coverage.get(slot.artist_id, 0) + 1

        raw, on_lineup = 0.0, []
        for slot in ev.lineup:
            aff = favs.get(slot.artist_id)
            if aff is None:
                continue
            per = 0.6 + 0.4 * aff                       # presence floor: any favorite counts big
            billing_boost = {1: 1.15, 2: 1.0, 3: 0.9}[slot.billing]
            novelty = (1 - self.cfg.novelty_decay) ** coverage.get(slot.artist_id, 0)
            raw += per * billing_boost * novelty
            on_lineup.append(slot.artist_id)

        value = math.tanh(raw / 4.0)     # smooth saturation: more favorites always helps, but less and less
        repeats = sum(1 for a in on_lineup if coverage.get(a, 0) > 0)
        names = [self.store.get_artist(a).name for a in on_lineup[:3]]
        ev_str = ((f"{len(on_lineup)} favorites on the lineup"
                   + (f" incl. {', '.join(names)}" if names else "")
                   + (f" ({repeats} already covered)" if repeats else ""))
                  if on_lineup else "no favorites on lineup")
        return self._pack("lineup_value", self.cfg.w_lineup_value, value, ev_str)

    def _cost_efficiency(self, ev: Event) -> ScoreFactor:
        km = _haversine_km(self.cfg.home_lat, self.cfg.home_lon, ev.lat, ev.lon)
        drive = km <= self.cfg.drive_km_threshold
        travel = self.cfg.drive_cost_flat if drive else self.cfg.fly_cost_flat
        total = ev.current_price + travel
        # $80 all-in ≈ perfect; $800+ ≈ terrible (log curve so mid prices spread out)
        value = max(0.0, min(1.0, 1.0 - (math.log10(max(total, 80)) - math.log10(80))
                                        / (math.log10(800) - math.log10(80))))
        mode = "drive" if drive else "fly"
        return self._pack("cost_efficiency", self.cfg.w_cost_efficiency, value,
                          f"${ev.current_price:.0f} ticket + ~${travel:.0f} {mode} ({km:.0f} km) ≈ ${total:.0f} all-in")

    def _chain_bonus(self, ev: Event) -> ScoreFactor:
        best, partner = 0.0, None
        for leg in self.store.get_circuit():
            other = self.store.get_event(leg.event_id)
            days = abs((ev.start_date - other.start_date).days)
            km = _haversine_km(ev.lat, ev.lon, other.lat, other.lon)
            if days <= 3 and km <= 200:
                closeness = (1 - days / 4) * (1 - km / 250)
                if closeness > best:
                    best, partner = closeness, other
        ev_str = (f"chains with {partner.name} ({partner.start_date})" if partner
                  else "no nearby legs to chain with")
        return self._pack("chain_bonus", self.cfg.w_chain_bonus, best, ev_str)

    def _crew(self, ev: Event) -> ScoreFactor:
        rsvps = self.store.rsvps_for_event(ev.id)
        going = sum(1 for r in rsvps if r.status == "going")
        interested = sum(1 for r in rsvps if r.status == "interested")
        value = min((going + 0.5 * interested) / 3.0, 1.0)   # 3 "going" = max
        ev_str = (f"{going} going, {interested} interested" if rsvps else "no crew signals yet")
        return self._pack("crew", self.cfg.w_crew, value, ev_str)

    def _production_fit(self, ev: Event) -> ScoreFactor:
        # unrated (3) contributes nothing; spectacle taste rewards 4-5, warehouse taste rewards 1-2
        value = 0.5 + ((ev.production - 3) / 2) * self.cfg.production_taste * 0.5
        tier = {1: "bare-bones", 2: "minimal", 3: "unrated/standard", 4: "big production", 5: "spectacle-tier"}[ev.production]
        return self._pack("production_fit", self.cfg.w_production_fit, value, tier)

    def _weather_comfort(self, ev: Event) -> ScoreFactor:
        comfort = CLIMATE.get(ev.city, [0.7] * 12)[ev.start_date.month - 1]
        month = ev.start_date.strftime("%b")
        return self._pack("weather_comfort", self.cfg.w_weather_comfort, comfort,
                          f"{month} in {ev.city}: {'prime' if comfort >= .85 else 'decent' if comfort >= .6 else 'rough'} season")

    # ---------- shared plumbing ----------

    def _pack(self, name: str, weight: float, value_0_to_1: float, evidence: str) -> ScoreFactor:
        return ScoreFactor(name=name, weight=weight,
                           contribution=round(weight * max(0.0, min(1.0, value_0_to_1)) * 100, 1),
                           evidence=evidence)