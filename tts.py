"""Text to Speech dengan suara Bahasa Indonesia yang natural.

Urutan pemilihan engine:
  1. edge-tts  -> suara neural Microsoft (id-ID-ArdiNeural / id-ID-GadisNeural). GRATIS, butuh internet.
  2. pyttsx3   -> suara bawaan OS. Offline, tapi di Windows sering tidak ada suara Indonesia
                  sehingga teks Indonesia dibaca dengan aksen Inggris.

Ganti engine lewat .env:  TTS_ENGINE=edge  |  TTS_ENGINE=offline
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
import threading

import config

log = logging.getLogger("tts")
_lock = threading.Lock()
_pyttsx_engine = None
_pygame_ready = False

# Suara Indonesia yang tersedia:
#   id-ID-ArdiNeural  (pria)
#   id-ID-GadisNeural (wanita)
EDGE_VOICE = os.getenv("EDGE_VOICE", "id-ID-ArdiNeural")
EDGE_RATE = os.getenv("EDGE_RATE", "+8%")   # contoh: "-10%", "+0%", "+20%"


# ---------------------------------------------------------------------- #
def _clean(text: str) -> str:
    """Buang markdown/URL supaya tidak dibaca sebagai 'bintang bintang'."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"[*_`#>|]", " ", text)
    text = re.sub(r"https?://\S+", "tautan", text)
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------- #
def _init_pygame() -> None:
    global _pygame_ready
    if _pygame_ready:
        return
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    import pygame

    pygame.mixer.init()
    _pygame_ready = True


def _play_file(path: str) -> None:
    import pygame

    _init_pygame()
    pygame.mixer.music.load(path)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        pygame.time.Clock().tick(20)
    pygame.mixer.music.unload()


async def _edge_synthesize(text: str, path: str) -> None:
    import edge_tts

    await edge_tts.Communicate(text, EDGE_VOICE, rate=EDGE_RATE).save(path)


def _say_edge(text: str) -> None:
    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp.close()
    try:
        asyncio.run(_edge_synthesize(text, tmp.name))
        _play_file(tmp.name)
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


# ---------------------------------------------------------------------- #
def _say_offline(text: str) -> None:
    global _pyttsx_engine
    import pyttsx3

    if _pyttsx_engine is None:
        _pyttsx_engine = pyttsx3.init()
        _pyttsx_engine.setProperty("rate", config.TTS_RATE)
        hint = config.TTS_VOICE_HINT.lower()
        for voice in _pyttsx_engine.getProperty("voices"):
            blob = f"{voice.id} {getattr(voice, 'name', '')}".lower()
            if hint and hint in blob:
                _pyttsx_engine.setProperty("voice", voice.id)
                break
    _pyttsx_engine.say(text)
    _pyttsx_engine.runAndWait()


# ---------------------------------------------------------------------- #
def say(text: str) -> None:
    print(f"[{config.AGENT_NAME}] {text}")
    if not config.TTS_ENABLED or not text.strip():
        return

    cleaned = _clean(text)
    engine = os.getenv("TTS_ENGINE", "edge").strip().lower()

    with _lock:
        if engine == "edge":
            try:
                _say_edge(cleaned)
                return
            except Exception as exc:  # noqa: BLE001
                print(f"   [TTS] edge-tts gagal: {type(exc).__name__}: {exc} -> coba suara offline")
                log.warning("edge-tts gagal (%s), fallback ke suara offline.", exc)
        try:
            _say_offline(cleaned)
        except Exception as exc:  # noqa: BLE001
            print(f"   [TTS] GAGAL TOTAL: {type(exc).__name__}: {exc}")
            log.error("TTS gagal total: %s", exc)


# ---------------------------------------------------------------------- #
if __name__ == "__main__":
    # Tes cepat:  python tts.py
    say("Halo, saya Leo, asisten pribadi Anda. Suara ini sudah berfungsi dengan baik.")