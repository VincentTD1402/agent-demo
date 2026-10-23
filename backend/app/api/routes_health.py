from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    """Liveness: tiến trình còn sống."""
    return {"status": "ok"}


@router.get("/ready")
async def ready(request: Request):
    """Readiness: đồ thị (Postgres + MCP) đã khởi tạo xong."""
    return {"status": "ready" if getattr(request.app.state, "graph", None) else "starting"}
