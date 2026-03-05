"""Subconscious memory extraction — runs after every conversation turn.

A lightweight LLM call (gpt-5-mini) reviews the exchange and extracts
durable facts/preferences into the AgentMemory table. Runs as a
fire-and-forget background task so the user never waits for it.
"""

from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI

from src.config import settings
from src.db import session_scope
from src.db.queries import delete_agent_memory, list_agent_memories, save_agent_memory

logger = logging.getLogger(__name__)

EXTRACTION_MODEL = "gpt-5-mini"

EXTRACTION_PROMPT = """\
You are a memory extraction system. Given a conversation exchange and existing memories, \
determine what NEW facts, preferences, or corrections to save.

EXISTING MEMORIES:
{memories}

USER MESSAGE:
{user_message}

ASSISTANT RESPONSE:
{assistant_response}

OUTPUT: JSON array of actions. Each action is one of:
- {{"action": "save", "key": "...", "content": "...", "category": "preference|fact|person|decision|workflow"}}
- {{"action": "update", "key": "existing_key", "content": "new content", "category": "..."}}
- {{"action": "delete", "key": "existing_key_thats_now_wrong"}}

RULES:
- Only extract DURABLE facts (not ephemeral like "I'm tired today")
- Prefer updating existing keys over creating new ones
- Use atomic facts: one fact per entry
- Category guide: preference (user likes/dislikes), fact (objective info), \
person (about contacts), decision (choices made), workflow (how user works)
- If nothing worth saving, return empty array: []
"""


async def extract_memories(user_message: str, assistant_response: str) -> int:
    """Call a cheap model to extract memories from a conversation exchange.

    Returns the number of memory actions applied.
    """
    # Load existing memories for context
    with session_scope() as session:
        existing = list_agent_memories(session, limit=50)
        if existing:
            mem_lines = [f"[{m.category}] {m.key}: {m.content}" for m in existing]
            memories_text = "\n".join(mem_lines)
        else:
            memories_text = "(none)"

    prompt = EXTRACTION_PROMPT.format(
        memories=memories_text,
        user_message=user_message,
        assistant_response=assistant_response[:2000],
    )

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model=EXTRACTION_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=1000,
    )

    raw = response.choices[0].message.content or "[]"

    # Strip markdown fences if present
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

    actions = json.loads(raw)
    if not isinstance(actions, list):
        return 0

    applied = 0
    with session_scope() as session:
        for action in actions:
            act = action.get("action")
            key = action.get("key", "")
            if not key:
                continue

            if act in ("save", "update"):
                content = action.get("content", "")
                category = action.get("category", "fact")
                if content:
                    save_agent_memory(session, key, content, category)
                    applied += 1
            elif act == "delete":
                delete_agent_memory(session, key)
                applied += 1

    return applied


async def extract_memories_background(user_message: str, assistant_response: str) -> None:
    """Fire-and-forget wrapper with error handling."""
    try:
        count = await extract_memories(user_message, assistant_response)
        if count > 0:
            logger.info("Subconscious memory: applied %d actions", count)
    except json.JSONDecodeError:
        logger.debug("Memory extraction returned invalid JSON", exc_info=True)
    except Exception:
        logger.debug("Memory extraction failed", exc_info=True)
