"""Session model for media.rip()."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Session(BaseModel):
    """Represents a browser session tracked via session ID."""

    id: str
    created_at: str
    last_seen: str
    job_count: int = Field(default=0)
