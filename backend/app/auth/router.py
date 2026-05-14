from __future__ import annotations
from datetime import timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from app.auth.utils import (
    create_access_token, create_refresh_token, decode_token,
    verify_password, hash_password, get_current_user
)
from app.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

_USERS: dict = {}


def _init_superuser():
    _USERS[settings.FIRST_SUPERUSER] = hash_password(settings.FIRST_SUPERUSER_PASSWORD)


_init_superuser()


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/login", response_model=TokenResponse)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    hashed = _USERS.get(form_data.username)
    if not hashed or not verify_password(form_data.password, hashed):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")
    access = create_access_token({"sub": form_data.username})
    refresh = create_refresh_token({"sub": form_data.username})
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/refresh")
async def refresh_token(body: RefreshRequest):
    payload = decode_token(body.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=400, detail="Invalid token type")
    access = create_access_token({"sub": payload["sub"]})
    return {"access_token": access, "token_type": "bearer"}


@router.post("/logout")
async def logout(current_user: str = Depends(get_current_user)):
    return {"message": "Logged out"}
