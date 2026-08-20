# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Anna Tchijova
"""Talk to ÍMPETU locally. Uses GEMINI_API_KEY from the environment.

    python3 try_it.py "tengo que responder tres mails que vengo pateando y no puedo empezar"

Prints the agent's words and, indented, every tool it calls - so you can see it
externalize your working memory in real time.
"""

from __future__ import annotations

import asyncio
import sys

from google.adk.runners import InMemoryRunner
from google.genai import types

from agent import root_agent

APP = "impetu"
USER = "anna"


async def one_turn(text: str) -> None:
    runner = InMemoryRunner(agent=root_agent, app_name=APP)
    session = await runner.session_service.create_session(
        app_name=APP, user_id=USER, state={"user_id": USER}
    )
    msg = types.Content(role="user", parts=[types.Part(text=text)])

    print(f"\nVOS: {text}\n" + "-" * 60)
    async for event in runner.run_async(
        user_id=USER, session_id=session.id, new_message=msg
    ):
        gm = getattr(event, "grounding_metadata", None)
        if gm and getattr(gm, "web_search_queries", None):
            print(f"    [google_search: {list(gm.web_search_queries)}]")
        if not event.content or not event.content.parts:
            continue
        for part in event.content.parts:
            if getattr(part, "text", None):
                print(f"IMPETU: {part.text.strip()}")
            elif getattr(part, "function_call", None):
                fc = part.function_call
                print(f"    [tool -> {fc.name}({dict(fc.args or {})})]")
            elif getattr(part, "function_response", None):
                fr = part.function_response
                print(f"    [tool <- {fr.name}: {fr.response}]")


if __name__ == "__main__":
    prompt = sys.argv[1] if len(sys.argv) > 1 else (
        "tengo que responder tres mails que vengo pateando hace una semana y no puedo empezar"
    )
    asyncio.run(one_turn(prompt))
