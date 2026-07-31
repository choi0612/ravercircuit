from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query

from app.services.events_service import EventsService, get_events_service

router = APIRouter(prefix="/api/v1", tags=["events"])

@router.get("/events")
def list_events(kind: str | None = None, city: str | None = None,
                month: int | None = Query(None, ge=1, le=12),
                limit: int = Query(25, ge=1, le=100),
                page_token: str | None = None,
                svc: EventsService = Depends(get_events_service)):
    items, next_token = svc.list_events(kind=kind, city=city, month=month,
                                        limit=limit, page_token=page_token)
    return {"items": items, "next_page_token": next_token}

@router.get("/events/{event_id}")
def get_event(event_id: str, svc: EventsService = Depends(get_events_service)):
    ev = svc.get_event(event_id)
    if ev is None:
        raise HTTPException(404, "event not found")
    return ev

@router.get("/events/{event_id}/updates")
def get_updates(event_id: str, start: datetime | None = None, end: datetime | None = None,
                svc: EventsService = Depends(get_events_service)):
    if svc.get_event(event_id) is None:
        raise HTTPException(404, "event not found")
    if start and end and start > end:
        raise HTTPException(422, "start must be <= end")
    return {"items": svc.get_updates(event_id, start, end)}

@router.get("/artists/{artist_id}/events")
def artist_events(artist_id: str, svc: EventsService = Depends(get_events_service)):
    return {"items": svc.events_for_artist(artist_id)}