"""Kiểm tra header X-API-Key dùng chung cho các router."""

import hmac

from fastapi import Depends, Header, HTTPException

from app.settings import Settings, get_settings


def require_api_key(x_api_key: str | None = Header(default=None), settings: Settings = Depends(get_settings)) -> None:
    if settings.api_key and not hmac.compare_digest(x_api_key or "", settings.api_key):
        raise HTTPException(status_code=401, detail="Thiếu hoặc sai X-API-Key")
