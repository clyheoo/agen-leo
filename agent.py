"""Otak agen: percakapan multi-turn + tool-use loop ke Claude API."""
from __future__ import annotations

import logging

from anthropic import Anthropic

import config
import tools

log = logging.getLogger("agent")


class Agent:
    def __init__(self) -> None:
        if not config.ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY belum diisi di file .env")
        self.client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self.history: list[dict] = []

    # ------------------------------------------------------------------ #
    def _trim(self) -> None:
        """Batasi panjang riwayat, tapi jangan memotong di tengah pasangan tool_use."""
        limit = config.HISTORY_TURNS * 2
        while len(self.history) > limit:
            self.history.pop(0)
        while self.history and self.history[0]["role"] != "user":
            self.history.pop(0)

    # ------------------------------------------------------------------ #
    def ask(self, user_text: str) -> str:
        self.history.append({"role": "user", "content": user_text})
        self._trim()

        final_text: list[str] = []

        for _ in range(config.MAX_TOOL_ITERATIONS):
            resp = self.client.messages.create(
                model=config.MODEL,
                max_tokens=config.MAX_TOKENS,
                system=config.SYSTEM_PROMPT,
                tools=tools.TOOL_SCHEMAS,
                messages=self.history,
            )

            text_parts = [b.text for b in resp.content if b.type == "text"]
            tool_calls = [b for b in resp.content if b.type == "tool_use"]
            if text_parts:
                final_text.extend(text_parts)

            self.history.append({"role": "assistant", "content": resp.content})

            if resp.stop_reason != "tool_use" or not tool_calls:
                break

            results = []
            for call in tool_calls:
                output = tools.execute(call.name, dict(call.input))
                print(f"   ⚙️  {call.name} → {output[:120]}")
                results.append(
                    {"type": "tool_result", "tool_use_id": call.id, "content": output}
                )
            self.history.append({"role": "user", "content": results})
        else:
            final_text.append("Maaf, langkahnya terlalu panjang jadi saya hentikan di sini.")

        return "\n".join(t.strip() for t in final_text if t.strip()) or "Selesai."

    # ------------------------------------------------------------------ #
    def reset(self) -> None:
        self.history.clear()