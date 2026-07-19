"""Text to Speech offline dengan pyttsx3 (pakai suara bawaan OS)."""
from __future__ import annotations

import logging
import re
import threading

import config

log = logging.getLogger("tts")
_lock = threading.Lock()
_engine = None


def _get_engine():
    global _engine
    if _engine is not None:
        return _engine
    import pyttsx3

    _engine = pyttsx3.init()
    _engine.setProperty("rate", config.TTS_RATE)
    hint = config.TTS_VOICE_HINT.lower()
    for voice in _engine.getProperty("voices"):
        blob = f"{voice.id} {getattr(voice, 'name', '')}".lower()
        if hint and hint in blob:
            _engine.setProperty("voice", voice.id)
            break
    return _engine


def _clean(text: str) -> str:
    """Buang markdown/simbol supaya tidak dibacakan sebagai 'bintang bintang'."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"[*_`#>|]", " ", text)
    text = re.sub(r"https?://\S+", "tautan", text)
    return re.sub(r"\s+", " ", text).strip()


def say(text: str) -> None:
    print(f"🤖 {config.AGENT_NAME}: {text}")
    if not config.TTS_ENABLED or not text.strip():
        return
    cleaned = _clean(text)
    with _lock:
        try:
            engine = _get_engine()
            engine.say(cleaned)
            engine.runAndWait()
        except Exception as exc:  # noqa: BLE001
            log.error("TTS gagal: %s", exc)