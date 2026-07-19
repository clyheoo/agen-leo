"""Otak agen — mendukung banyak provider LLM.

Atur di .env:
    LLM_PROVIDER=groq        # groq | gemini | openrouter | anthropic
    MODEL=llama-3.3-70b-versatile
    GROQ_API_KEY=...         (atau GEMINI_API_KEY / OPENROUTER_API_KEY / ANTHROPIC_API_KEY)

Semua provider selain Anthropic diakses lewat endpoint yang kompatibel dengan OpenAI,
jadi cukup satu jalur kode. tools.py TIDAK perlu diubah sama sekali.
"""
from __future__ import annotations

import json
import logging
import os

import config
import tools

log = logging.getLogger("agent")

PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()

# base_url + nama environment variable untuk key tiap provider
PROVIDERS = {
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/", "GEMINI_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
}


# ====================================================================== #
def _to_openai_tools() -> list[dict]:
    """Ubah skema tool gaya Anthropic menjadi gaya OpenAI function-calling."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in tools.TOOL_SCHEMAS
    ]


# ====================================================================== #
class Agent:
    def __init__(self) -> None:
        self.history: list[dict] = []
        self.provider = PROVIDER

        if self.provider == "anthropic":
            from anthropic import Anthropic

            if not config.ANTHROPIC_API_KEY:
                raise RuntimeError("ANTHROPIC_API_KEY belum diisi di .env")
            self.client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
        else:
            if self.provider not in PROVIDERS:
                raise RuntimeError(
                    f"LLM_PROVIDER '{self.provider}' tidak dikenal. "
                    f"Pilihan: anthropic, {', '.join(PROVIDERS)}"
                )
            from openai import OpenAI

            base_url, key_name = PROVIDERS[self.provider]
            api_key = os.getenv(key_name, "").strip()
            if not api_key:
                raise RuntimeError(f"{key_name} belum diisi di .env")
            self.client = OpenAI(api_key=api_key, base_url=base_url)
            self.oa_tools = _to_openai_tools()

    # ------------------------------------------------------------------ #
    def _trim(self) -> None:
        limit = config.HISTORY_TURNS * 2
        while len(self.history) > limit:
            self.history.pop(0)
        # jangan sampai riwayat diawali potongan tool_result yatim
        while self.history and self.history[0].get("role") in ("tool", "assistant"):
            self.history.pop(0)

    # ------------------------------------------------------------------ #
    def ask(self, user_text: str) -> str:
        if self.provider == "anthropic":
            return self._ask_anthropic(user_text)
        return self._ask_openai_compat(user_text)

    # ---------------------------- Anthropic ---------------------------- #
    def _ask_anthropic(self, user_text: str) -> str:
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
            final_text.extend(b.text for b in resp.content if b.type == "text")
            tool_calls = [b for b in resp.content if b.type == "tool_use"]
            self.history.append({"role": "assistant", "content": resp.content})

            if resp.stop_reason != "tool_use" or not tool_calls:
                break

            results = []
            for call in tool_calls:
                output = tools.execute(call.name, dict(call.input))
                print(f"   [tool] {call.name} -> {output[:120]}")
                results.append({"type": "tool_result", "tool_use_id": call.id, "content": output})
            self.history.append({"role": "user", "content": results})
        else:
            final_text.append("Langkahnya terlalu panjang, saya hentikan di sini.")

        return "\n".join(t.strip() for t in final_text if t.strip()) or "Selesai."

    # ------------------- Groq / Gemini / OpenRouter -------------------- #
    def _extra_params(self) -> dict:
        """Parameter khusus per model — terutama untuk menekan latensi."""
        extra = {}
        # gpt-oss adalah model reasoning: secara default ia "berpikir panjang"
        # sebelum menjawab. Untuk asisten suara itu terlalu lambat.
        if "gpt-oss" in config.MODEL:
            extra["reasoning_effort"] = os.getenv("REASONING_EFFORT", "low")
        return extra

    def _ask_openai_compat(self, user_text: str) -> str:
        self.history.append({"role": "user", "content": user_text})
        self._trim()
        final_text: list[str] = []

        for _ in range(config.MAX_TOOL_ITERATIONS):
            try:
                resp = self.client.chat.completions.create(
                    model=config.MODEL,
                    max_tokens=config.MAX_TOKENS,
                    messages=[{"role": "system", "content": config.SYSTEM_PROMPT}] + self.history,
                    tools=self.oa_tools,
                    **self._extra_params(),
                )
            except Exception as exc:  # noqa: BLE001
                log.error("Panggilan LLM gagal: %s", exc)
                # Tampilkan error aslinya di terminal supaya bisa didiagnosis.
                print(f"   [ERROR LLM] {type(exc).__name__}: {exc}")
                if self.history:
                    self.history.pop()
                if "tool_use_failed" in str(exc):
                    return "Maaf, saya gagal memanggil perintah itu. Coba ucapkan lebih spesifik."
                if "rate" in str(exc).lower() or "429" in str(exc):
                    return "Batas pemakaian gratis tercapai. Tunggu sebentar lalu coba lagi."
                return "Maaf, model sedang bermasalah. Cek pesan error di terminal."

            msg = resp.choices[0].message
            if msg.content:
                final_text.append(msg.content)

            calls = msg.tool_calls or []

            # PENTING: kirim kunci "tool_calls" HANYA kalau memang ada.
            # Mengirim tool_calls: null membuat sebagian provider menolak request
            # pada giliran berikutnya.
            entry: dict = {"role": "assistant", "content": msg.content or ""}
            if calls:
                entry["tool_calls"] = [
                    {
                        "id": c.id,
                        "type": "function",
                        "function": {"name": c.function.name, "arguments": c.function.arguments},
                    }
                    for c in calls
                ]
            self.history.append(entry)

            if not calls:
                break

            for call in calls:
                try:
                    args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                output = tools.execute(call.function.name, args)
                print(f"   [tool] {call.function.name} -> {output[:120]}")
                self.history.append(
                    {"role": "tool", "tool_call_id": call.id, "content": output}
                )
        else:
            final_text.append("Langkahnya terlalu panjang, saya hentikan di sini.")

        return "\n".join(t.strip() for t in final_text if t.strip()) or "Selesai."

    # ------------------------------------------------------------------ #
    def reset(self) -> None:
        self.history.clear()