import secrets

from fastapi import Depends, Header, HTTPException, Request, status

from app.config import Settings, get_settings


async def require_api_key(
    x_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    """Nếu API_KEY được cấu hình thì bắt buộc header X-API-Key khớp."""
    if not settings.api_key:
        return
    if not x_api_key or not secrets.compare_digest(x_api_key, settings.api_key):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid api key")


def get_graph(request: Request):
    return request.app.state.graph
