"""Groq-backed voice intent classification for ambiguous transcripts."""

from __future__ import annotations

import json
import logging
import re
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from utils.config import get_groq_api_key, get_groq_model, VOICE_INTENT_GROQ_ENABLED

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])

RunStatus = Literal["idle", "active", "waiting_for_user"]
VoiceIntent = Literal["resume", "new_task"]

RESUME_PATTERN = re.compile(
    r"^\s*(continue|resume|done|go ahead|proceed|i'?m done|finished|all set|ready)\s*[.!]?\s*$",
    re.IGNORECASE,
)
RESUME_PREFIX = re.compile(
    r"^(please\s+)?(continue|resume|go ahead|proceed)(\s+please)?[.!]?$",
    re.IGNORECASE,
)
RESUME_SHORT = re.compile(
    r"^(i'?m\s+)?(done|finished|ready|logged in|signed in)[.!]?$",
    re.IGNORECASE,
)


class ClassifyIntentRequest(BaseModel):
    text: str = Field(min_length=1)
    run_status: RunStatus = Field(alias="runStatus")

    model_config = {"populate_by_name": True}


class ClassifyIntentResponse(BaseModel):
    intent: VoiceIntent
    task_text: str = Field(alias="taskText")

    model_config = {"populate_by_name": True}


def classify_intent_locally(text: str, run_status: RunStatus) -> VoiceIntent | None:
    normalized = " ".join(text.strip().lower().split())
    if not normalized:
        return None

    if run_status != "waiting_for_user":
        return "new_task"

    if RESUME_PATTERN.match(normalized):
        return "resume"

    if RESUME_PREFIX.match(normalized) or RESUME_SHORT.match(normalized):
        return "resume"

    if len(normalized.split()) >= 5:
        return "new_task"

    return None


async def classify_intent_with_groq(
    text: str,
    run_status: RunStatus,
) -> ClassifyIntentResponse | None:
    from utils.config import VOICE_INTENT_GROQ_ENABLED

    if not get_groq_api_key() or not VOICE_INTENT_GROQ_ENABLED:
        return None

    try:
        from groq import Groq

        client = Groq(api_key=get_groq_api_key())
        prompt = (
            "Classify the user's spoken command for a browser automation agent.\n"
            f"Run status: {run_status}\n"
            f"Transcript: {text}\n\n"
            "Return JSON only: "
            '{"intent":"resume"|"new_task","taskText":"..."}\n'
            "- Use intent=resume only for short continue/done/resume style commands while waiting for the user.\n"
            "- Use intent=new_task for shopping tasks or longer instructions.\n"
            "- taskText should be the cleaned task text (or the original transcript for resume)."
        )

        completion = client.chat.completions.create(
            model=get_groq_model(),
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=120,
        )

        content = completion.choices[0].message.content or ""
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            return None

        payload = json.loads(match.group())
        intent = payload.get("intent")
        task_text = payload.get("taskText") or text

        if intent not in {"resume", "new_task"}:
            return None

        return ClassifyIntentResponse(intent=intent, task_text=str(task_text).strip())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Groq voice intent classification failed: %s", exc)
        return None


@router.post("/classify-intent", response_model=ClassifyIntentResponse)
async def classify_intent(request: ClassifyIntentRequest) -> ClassifyIntentResponse:
    local = classify_intent_locally(request.text, request.run_status)
    if local is not None:
        return ClassifyIntentResponse(intent=local, task_text=request.text.strip())

    groq = await classify_intent_with_groq(request.text, request.run_status)
    if groq is not None:
        return groq

    if request.run_status == "waiting_for_user" and len(request.text.split()) <= 3:
        return ClassifyIntentResponse(intent="resume", task_text=request.text.strip())

    return ClassifyIntentResponse(intent="new_task", task_text=request.text.strip())
