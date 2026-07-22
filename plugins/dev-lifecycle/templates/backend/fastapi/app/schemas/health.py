"""Schemas for the liveness/readiness probes. `HealthStatus`'s shape
(`{"status": "..."}`) matches packages/api-client/openapi.sample.json's
existing `HealthStatus` fixture schema (see that file/README) so the
eventual live-schema swap in Step 4 doesn't reshape this one field."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class HealthStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str


class ReadinessStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
