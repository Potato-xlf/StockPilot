from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"]
    database: Literal["ok"]


class DataSourceStatusResponse(BaseModel):
    name: str
    status: Literal["ok", "error"]
    latency_ms: float
    message: str
