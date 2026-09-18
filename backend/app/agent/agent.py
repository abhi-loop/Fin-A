"""Agent loop: the LLM chooses tools, Python executes them and does the maths."""
import json
import re
from typing import Any

from sqlalchemy.orm import Session

from ..config import ANTHROPIC_API_KEY, MODEL
from ..tools import TOOL_SCHEMAS, run_tool
from . import fallback
from .prompts import SYSTEM_PROMPT

MAX_TURNS = 6


def _extract_json(text: str) -> dict[str, Any] | None:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
    return None


def answer(db: Session, user_id: int, question: str) -> dict[str, Any]:
    """Return a structured answer. Falls back to rules when no API key is set."""
    if not ANTHROPIC_API_KEY:
        return fallback.answer(db, user_id, question)

    try:
        from anthropic import Anthropic
    except ImportError:
        return fallback.answer(db, user_id, question)

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
    used: list[str] = []

    try:
        for _ in range(MAX_TURNS):
            resp = client.messages.create(
                model=MODEL, max_tokens=1500, system=SYSTEM_PROMPT,
                tools=TOOL_SCHEMAS, messages=messages,
            )
            messages.append({"role": "assistant", "content": resp.content})

            calls = [b for b in resp.content if b.type == "tool_use"]
            if not calls:
                text = "".join(b.text for b in resp.content if b.type == "text")
                parsed = _extract_json(text)
                if parsed:
                    parsed.setdefault("metrics", [])
                    parsed.setdefault("insights", [])
                    parsed.setdefault("sources", [])
                    parsed["tools_used"] = used
                    return parsed
                return {"answer": text or "I could not analyse that.",
                        "metrics": [], "insights": [], "sources": [],
                        "tools_used": used}

            results = []
            for call in calls:
                used.append(call.name)
                try:
                    out = run_tool(call.name, db, user_id, **(call.input or {}))
                except Exception as exc:  # tool failure is data, not a crash
                    out = {"error": str(exc)}
                results.append({"type": "tool_result", "tool_use_id": call.id,
                                "content": json.dumps(out, default=str)})
            messages.append({"role": "user", "content": results})
    except Exception:
        pass

    return fallback.answer(db, user_id, question)
