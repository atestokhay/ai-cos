"""Internal model execution routes. All endpoints require X-Internal-Secret header."""

import json
import logging
from typing import AsyncIterator

from fastapi import APIRouter, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from core.contracts.model_router import ModelCallRequest, ModelCallResponse
from core.model_router.application.route_request import RouteRequest

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/model", tags=["model"])

_AUTH_HEADER = "x-internal-secret"


def _check_auth(request: Request, x_internal_secret: str | None) -> None:
    expected = request.app.state.internal_secret
    if x_internal_secret is None or x_internal_secret != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")


def _resolve_spec(request: Request, call_request: ModelCallRequest):
    route: RouteRequest = request.app.state.route_request
    candidates = route(call_request)
    if not candidates:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"no enabled model found for model_id='{call_request.model_id}'",
        )
    return candidates[0]


@router.post("/execute", response_model=ModelCallResponse)
def execute(
    call_request: ModelCallRequest,
    request: Request,
    x_internal_secret: str | None = Header(default=None),
) -> ModelCallResponse:
    _check_auth(request, x_internal_secret)
    spec = _resolve_spec(request, call_request)
    pipeline = request.app.state.pipeline
    return pipeline.execute(call_request, spec)


@router.post("/stream")
def stream(
    call_request: ModelCallRequest,
    request: Request,
    x_internal_secret: str | None = Header(default=None),
) -> StreamingResponse:
    _check_auth(request, x_internal_secret)
    spec = _resolve_spec(request, call_request)
    pipeline = request.app.state.pipeline

    def _generate():
        from core.model_router.domain.streaming import (
            StreamError,
            TextChunk,
            ToolCallChunk,
            UsageMetadata,
        )
        import dataclasses

        for event in pipeline.stream(call_request, spec):
            data = dataclasses.asdict(event)
            data["type"] = type(event).__name__
            yield f"data: {json.dumps(data)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(_generate(), media_type="text/event-stream")
