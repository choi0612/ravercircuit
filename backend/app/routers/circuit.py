from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.models.domain import CircuitLeg, Friend, FriendRsvp, LegStatus, RsvpStatus
from app.services.events_service import EventsService, get_events_service

router = APIRouter(prefix="/api/v1", tags=["circuit"])

class LegCreate(BaseModel):
    event_id: str
    status: LegStatus = LegStatus.PLANNED

class RsvpCreate(BaseModel):
    friend_id: str
    status: RsvpStatus

class FriendCreate(BaseModel):
    id: str
    name: str

@router.get("/circuit")
def get_circuit(svc: EventsService = Depends(get_events_service)):
    return {"legs": svc.get_circuit()}

@router.post("/circuit/legs", status_code=201)
def add_leg(body: LegCreate, svc: EventsService = Depends(get_events_service)):
    if svc.get_event(body.event_id) is None:
        raise HTTPException(404, "event not found")
    leg = CircuitLeg(event_id=body.event_id, status=body.status, added_at=datetime.now())
    if not svc.add_leg(leg):
        raise HTTPException(409, "event already in circuit")
    return leg

@router.delete("/circuit/legs/{event_id}")
def remove_leg(event_id: str, svc: EventsService = Depends(get_events_service)):
    if not svc.remove_leg(event_id):
        raise HTTPException(404, "event not in circuit")
    return {"removed": event_id}

@router.get("/friends")
def list_friends(svc: EventsService = Depends(get_events_service)):
    return {"items": svc.get_friends()}

@router.post("/friends", status_code=201)
def add_friend(body: FriendCreate, svc: EventsService = Depends(get_events_service)):
    svc.add_friend(Friend(id=body.id, name=body.name))
    return body

@router.get("/events/{event_id}/rsvps")
def event_rsvps(event_id: str, svc: EventsService = Depends(get_events_service)):
    if svc.get_event(event_id) is None:
        raise HTTPException(404, "event not found")
    return {"items": svc.rsvps_for_event(event_id)}

@router.post("/events/{event_id}/rsvps", status_code=201)
def add_rsvp(event_id: str, body: RsvpCreate, svc: EventsService = Depends(get_events_service)):
    if svc.get_event(event_id) is None:
        raise HTTPException(404, "event not found")
    rsvp = FriendRsvp(friend_id=body.friend_id, event_id=event_id, status=body.status)
    svc.add_rsvp(rsvp)
    return rsvp