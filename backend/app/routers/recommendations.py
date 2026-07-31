from fastapi import APIRouter, Depends, Query

from app.services.events_service import EventsService, get_events_service

router = APIRouter(prefix="/api/v1", tags=["recommendations"])

@router.get("/recommendations")
def recommendations(limit: int = Query(25, ge=1, le=200),
                    svc: EventsService = Depends(get_events_service)):
    return {"items": svc.recommendations()[:limit]}