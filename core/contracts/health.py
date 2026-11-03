"""Operational health response. This is not a project-wide API or error contract."""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok", "unavailable"]
