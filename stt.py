"""Speech to Text: dua backend (Google online / Whisper offline) di balik satu API."""
from __future__ import annotations

import logging
import tempfile
import os

import speech_recognition as sr

import config

log = logging.getLogger("stt")


class SpeechListener:
    def __init__(self) -> None:
        self.recognizer = sr.Recognizer()
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.pause_threshold = 0.8
        self.mic = sr.Microphone(device_index=config.MIC_INDEX)
        self._whisper = None

        with self.mic as source:
            log.info("Kalibrasi noise sekitar (1 detik)...")
            self.recognizer.adjust_for_ambient_noise(source, duration=1.0)

        if config.STT_ENGINE == "whisper":
            self._load_whisper()

    # ------------------------------------------------------------------ #
    def _load_whisper(self) -> None:
        from faster_whisper import WhisperModel  # import lazy, berat

        log.info("Memuat model Whisper '%s'...", config.WHISPER_MODEL)
        self._whisper = WhisperModel(config.WHISPER_MODEL, device="auto", compute_type="int8")

    # ------------------------------------------------------------------ #
    def listen(self, timeout: float | None = None) -> str | None:
        """Rekam satu kalimat lalu kembalikan teksnya. None kalau gagal/sunyi."""
        try:
            with self.mic as source:
                audio = self.recognizer.listen(
                    source, timeout=timeout, phrase_time_limit=config.PHRASE_TIME_LIMIT
                )
        except sr.WaitTimeoutError:
            return None

        try:
            if config.STT_ENGINE == "whisper":
                return self._transcribe_whisper(audio)
            return self.recognizer.recognize_google(audio, language=config.LANGUAGE)
        except sr.UnknownValueError:
            return None
        except Exception as exc:  # noqa: BLE001
            log.error("STT error: %s", exc)
            return None

    # ------------------------------------------------------------------ #
    def _transcribe_whisper(self, audio) -> str | None:
        if self._whisper is None:
            self._load_whisper()

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        try:
            tmp.write(audio.get_wav_data())
            tmp.close()
            segments, _ = self._whisper.transcribe(
                tmp.name, language=config.LANGUAGE.split("-")[0], vad_filter=True
            )
            text = " ".join(s.text for s in segments).strip()
            return text or None
        finally:
            os.unlink(tmp.name)


def list_microphones() -> list[str]:
    return list(sr.Microphone.list_microphone_names())