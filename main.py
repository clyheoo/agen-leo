"""Entry point agen suara.

Pemakaian:
    python main.py                 # mode suara (wake word)
    python main.py --text          # mode ketik, enak buat debugging tanpa mic
    python main.py --list-mics     # lihat daftar mikrofon + indeksnya
    python main.py --once "buka chrome"   # eksekusi satu perintah lalu keluar
"""
from __future__ import annotations

import argparse
import logging
import sys

import config
import tts


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.FileHandler(config.LOG_FILE, encoding="utf-8")],
    )


def strip_wake_word(text: str) -> tuple[bool, str]:
    """Kembalikan (terpanggil?, sisa perintah setelah wake word)."""
    low = text.lower().strip()
    for w in config.WAKE_WORDS:
        if low.startswith(w):
            return True, text[len(w):].lstrip(" ,.!?")
        if w in low:
            return True, text[low.index(w) + len(w):].lstrip(" ,.!?")
    return False, text


def is_stop(text: str) -> bool:
    low = text.lower().strip()
    return any(s in low for s in config.STOP_WORDS)


# ---------------------------------------------------------------------- #
def run_text_mode(agent) -> None:
    print(f"Mode teks. Ketik perintah, atau 'keluar' untuk berhenti.\n")
    while True:
        try:
            text = input("👤 Anda: ").strip()
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
    tts.say(f"{config.AGENT_NAME} siap. Panggil saya dengan menyebut {config.WAKE_WORDS[0]}.")

    while True:
        print(f"\n🎧 Menunggu wake word ({'/'.join(config.WAKE_WORDS)})...")
        heard = listener.listen(timeout=None)
        if not heard:
            continue
        print(f"👤 Terdengar: {heard}")

        if is_stop(heard):
            tts.say("Baik, agen dimatikan.")
            return

        called, command = strip_wake_word(heard)
        if not called:
            continue

        # Wake word saja tanpa perintah -> tanya balik lalu dengarkan sekali lagi
        if not command:
            tts.say("Ya, ada yang bisa saya bantu?")
            command = listener.listen(timeout=8) or ""
            print(f"👤 Perintah: {command}")
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
    parser = argparse.ArgumentParser(description="Agen AI suara pribadi")
    parser.add_argument("--text", action="store_true", help="mode ketik tanpa mikrofon")
    parser.add_argument("--list-mics", action="store_true", help="tampilkan daftar mikrofon")
    parser.add_argument("--once", metavar="PERINTAH", help="jalankan satu perintah lalu keluar")
    args = parser.parse_args()

    setup_logging()

    if args.list_mics:
        from stt import list_microphones

        for i, name in enumerate(list_microphones()):
            print(f"[{i}] {name}")
        return

    from agent import Agent

    try:
        agent = Agent()
    except RuntimeError as exc:
        print(f"❌ {exc}")
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