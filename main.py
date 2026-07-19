"""Entry point agen suara.

Pemakaian:
    python main.py                 # mode suara (wake word)
    python main.py --open          # mode suara TANPA wake word (semua ucapan = perintah)
    python main.py --text          # mode ketik, buat debugging tanpa mic
    python main.py --list-mics     # lihat daftar mikrofon + indeksnya
    python main.py --once "buka chrome"
"""
from __future__ import annotations

import argparse
import difflib
import logging
import os
import re
import sys

import config
import tts

# Seberapa mirip hasil STT harus dengan wake word agar dianggap panggilan.
# 1.0 = harus persis. 0.65 cukup longgar untuk menangkap "lio", "leyo", "neo".
WAKE_RATIO = float(os.getenv("WAKE_RATIO", "0.65"))
# Kalau false, setiap kalimat langsung dianggap perintah (tanpa perlu sebut "Leo")
REQUIRE_WAKE_WORD = os.getenv("REQUIRE_WAKE_WORD", "true").strip().lower() not in ("0", "false", "no")


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.FileHandler(config.LOG_FILE, encoding="utf-8")],
    )


def _norm(text: str) -> str:
    return re.sub(r"[^\w\s]", "", text.lower()).strip()


def strip_wake_word(text: str) -> tuple[bool, str]:
    """Kembalikan (terpanggil?, sisa perintah).

    Deteksi bertahap:
      1. Wake word muncul persis di dalam kalimat.
      2. Kata-kata awal MIRIP wake word (toleransi salah dengar STT).
    """
    if not REQUIRE_WAKE_WORD:
        return True, text.strip()

    low = _norm(text)
    if not low:
        return False, ""

    # --- 1. kecocokan persis -------------------------------------------
    for w in config.WAKE_WORDS:
        wn = _norm(w)
        if low == wn:
            return True, ""
        if low.startswith(wn + " "):
            return True, low[len(wn):].strip()
        if f" {wn} " in f" {low} ":
            idx = low.index(wn) + len(wn)
            return True, low[idx:].strip()

    # --- 2. kecocokan mirip pada 1-2 kata pertama ----------------------
    words = low.split()
    for n in (1, 2):
        if len(words) < n:
            break
        head = " ".join(words[:n])
        for w in config.WAKE_WORDS:
            ratio = difflib.SequenceMatcher(None, head, _norm(w)).ratio()
            if ratio >= WAKE_RATIO:
                logging.info("Wake word mirip: '%s' ~ '%s' (%.2f)", head, w, ratio)
                return True, " ".join(words[n:]).strip()

    return False, text


def is_stop(text: str) -> bool:
    low = _norm(text)
    return any(_norm(s) in low for s in config.STOP_WORDS)


# ---------------------------------------------------------------------- #
def run_text_mode(agent) -> None:
    print("Mode teks. Ketik perintah, atau 'keluar' untuk berhenti.\n")
    while True:
        try:
            text = input("Anda: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            continue
        if is_stop(text):
            break
        tts.say(agent.ask(text))
    print("Sampai jumpa.")


def run_voice_mode(agent) -> None:
    from stt import SpeechListener

    listener = SpeechListener()

    if REQUIRE_WAKE_WORD:
        tts.say(f"{config.AGENT_NAME} siap. Panggil saya dengan menyebut {config.WAKE_WORDS[0]}.")
    else:
        tts.say(f"{config.AGENT_NAME} siap. Mode terbuka, langsung sebutkan perintah Anda.")

    while True:
        label = "wake word" if REQUIRE_WAKE_WORD else "perintah"
        print(f"\n[ ] Mendengarkan {label}...")

        heard = listener.listen(timeout=None)
        if not heard:
            continue
        print(f"[Anda] {heard}")

        if is_stop(heard):
            tts.say("Baik, agen dimatikan.")
            return

        called, command = strip_wake_word(heard)
        if not called:
            print("      (bukan panggilan untuk saya, diabaikan)")
            continue

        # Wake word saja tanpa perintah -> tanya balik lalu dengarkan lagi
        if not command:
            tts.say("Ya, ada yang bisa saya bantu?")
            command = listener.listen(timeout=10) or ""
            print(f"[Perintah] {command}")
            if not command:
                tts.say("Saya tidak menangkap perintahnya.")
                continue

        if is_stop(command):
            tts.say("Baik, agen dimatikan.")
            return

        try:
            tts.say(agent.ask(command))
        except Exception as exc:  # noqa: BLE001
            logging.exception("Gagal memproses perintah")
            tts.say(f"Terjadi kesalahan: {exc}")


# ---------------------------------------------------------------------- #
def main() -> None:
    global REQUIRE_WAKE_WORD

    parser = argparse.ArgumentParser(description="Agen AI suara pribadi")
    parser.add_argument("--text", action="store_true", help="mode ketik tanpa mikrofon")
    parser.add_argument("--open", action="store_true", help="mode suara tanpa wake word")
    parser.add_argument("--list-mics", action="store_true", help="tampilkan daftar mikrofon")
    parser.add_argument("--once", metavar="PERINTAH", help="jalankan satu perintah lalu keluar")
    args = parser.parse_args()

    setup_logging()

    if args.open:
        REQUIRE_WAKE_WORD = False

    if args.list_mics:
        from stt import list_microphones

        for i, name in enumerate(list_microphones()):
            print(f"[{i}] {name}")
        return

    from agent import Agent

    try:
        agent = Agent()
    except RuntimeError as exc:
        print(f"[X] {exc}")
        sys.exit(1)

    print(f"=== {config.AGENT_NAME} | model {config.MODEL} | workspace {config.WORKSPACE} ===")

    if args.once:
        tts.say(agent.ask(args.once))
    elif args.text:
        run_text_mode(agent)
    else:
        try:
            run_voice_mode(agent)
        except KeyboardInterrupt:
            print("\nDihentikan.")


if __name__ == "__main__":
    main()