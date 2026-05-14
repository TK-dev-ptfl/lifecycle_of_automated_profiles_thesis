from __future__ import annotations
from datetime import datetime
from typing import Any, Optional
from uuid import UUID
from pydantic import BaseModel
from app.models.bot import BotMode, BotStatus, CommunicationMode, BehaviourPattern, BotState


class BotParameters(BaseModel):
    actions_per_hour: int = 10
    active_hours: str = "08:00-22:00"
    rest_days: list = []
    location: str = "US"
    min_delay_seconds: int = 5
    max_delay_seconds: int = 30
    max_follows_per_day: int = 50
    max_likes_per_day: int = 100
    stealth_mode: bool = True
    retry_on_error: bool = True


class BotBase(BaseModel):
    name: str
    platform_id: Optional[UUID] = None
    identity_value: Optional[str] = None
    profile_name: Optional[str] = None
    profile_password: Optional[str] = None
    platform_name: Optional[str] = None
    is_healthy: bool = True
    sandbox_ids: list[UUID] = []
    state: BotState = BotState.not_active
    skeleton: str = "engagement_farmer"
    mode: BotMode = BotMode.growing
    communication_mode: CommunicationMode = CommunicationMode.official_api
    behaviour_pattern: BehaviourPattern = BehaviourPattern.passive
    parameters: dict = {}
    algorithm_config: dict = {}


class BotCreate(BotBase):
    identity_id: Optional[UUID] = None
    password: Optional[str] = None
    proxy_id: Optional[UUID] = None


class BotUpdate(BaseModel):
    name: Optional[str] = None
    identity_value: Optional[str] = None
    profile_name: Optional[str] = None
    profile_password: Optional[str] = None
    platform_name: Optional[str] = None
    is_healthy: Optional[bool] = None
    sandbox_ids: Optional[list[UUID]] = None
    state: Optional[BotState] = None
    skeleton: Optional[str] = None
    mode: Optional[BotMode] = None
    communication_mode: Optional[CommunicationMode] = None
    behaviour_pattern: Optional[BehaviourPattern] = None
    parameters: Optional[dict] = None
    algorithm_config: Optional[dict] = None
    identity_id: Optional[UUID] = None
    password: Optional[str] = None
    proxy_id: Optional[UUID] = None
    task_id: Optional[UUID] = None


class BotResponse(BotBase):
    id: UUID
    identity_id: Optional[UUID]
    password: Optional[str]
    proxy_id: Optional[UUID]
    status: BotStatus
    task_id: Optional[UUID]
    flag_count: int
    last_active: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BotSetModeRequest(BaseModel):
    mode: BotMode


class BotStatsResponse(BaseModel):
    actions_today: int
    actions_lifetime: int
    success_rate: float
    uptime_hours: float
    flag_count: int


class LogResponse(BaseModel):
    id: UUID
    bot_id: UUID
    task_id: Optional[UUID]
    level: str
    category: str
    message: str
    metadata: dict = {}
    created_at: datetime

    model_config = {"from_attributes": True}
