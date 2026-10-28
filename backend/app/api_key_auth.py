"""Kiểm tra khoá truy cập dùng chung cho các router: X-API-Key (chung) và X-Staff-Key (nhân viên)."""

import hmac

from fastapi import Depends, Header, HTTPException

from app.settings import Settings, get_settings


def require_api_key(x_api_key: str | None = Header(default=None), settings: Settings = Depends(get_settings)) -> None:
    if settings.api_key and not hmac.compare_digest(x_api_key or "", settings.api_key):
        raise HTTPException(status_code=401, detail="Thiếu hoặc sai X-API-Key")


def require_staff(x_staff_key: str | None = Header(default=None), settings: Settings = Depends(get_settings)) -> None:
    if not settings.staff_api_key:
        raise HTTPException(status_code=503, detail="API nhân viên chưa được bật (STAFF_API_KEY trống)")
    if not hmac.compare_digest(x_staff_key or "", settings.staff_api_key):
        raise HTTPException(status_code=401, detail="Thiếu hoặc sai X-Staff-Key")
