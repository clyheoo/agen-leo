"""Konfigurasi terpusat. Semua nilai bisa dioverride lewat file .env"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _bool(key: str, default: bool = False) -> bool:
    return os.getenv(key, str(default)).strip().lower() in ("1", "true", "yes", "y")


# --- LLM ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL = os.getenv("MODEL", "claude-sonnet-5")
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "1500"))
MAX_TOOL_ITERATIONS = int(os.getenv("MAX_TOOL_ITERATIONS", "8"))

# --- Identitas agen ---
AGENT_NAME = os.getenv("AGENT_NAME", "Zeo")
WAKE_WORDS = [w.strip().lower() for w in os.getenv("WAKE_WORDS", "zeo,hai zeo,oke zeo").split(",") if w.strip()]
STOP_WORDS = [w.strip().lower() for w in os.getenv("STOP_WORDS", "berhenti,matikan agen,keluar").split(",") if w.strip()]
LANGUAGE = os.getenv("LANGUAGE", "id-ID")

# --- Speech to Text ---
# "whisper"  -> offline, akurat, butuh faster-whisper (rekomendasi)
# "google"   -> online gratis via SpeechRecognition, setup paling ringan
STT_ENGINE = os.getenv("STT_ENGINE", "google")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")   # tiny|base|small|medium
MIC_INDEX = os.getenv("MIC_INDEX")
MIC_INDEX = int(MIC_INDEX) if MIC_INDEX not in (None, "") else None
PHRASE_TIME_LIMIT = int(os.getenv("PHRASE_TIME_LIMIT", "12"))

# --- Text to Speech ---
TTS_ENABLED = _bool("TTS_ENABLED", True)
TTS_RATE = int(os.getenv("TTS_RATE", "180"))
TTS_VOICE_HINT = os.getenv("TTS_VOICE_HINT", "indonesia")

# --- Keamanan ---
# Shell/eksekusi perintah sistem MATI secara default. Nyalakan hanya jika paham risikonya.
ALLOW_SHELL = _bool("ALLOW_SHELL", False)
# True = setiap aksi berisiko (shell, hapus file, tulis file) minta konfirmasi suara/ketik
CONFIRM_RISKY_ACTIONS = _bool("CONFIRM_RISKY_ACTIONS", True)
# Agen hanya boleh baca/tulis file di dalam folder ini
_ws = os.getenv("WORKSPACE", "").strip() or str(Path.home() / "AgentWorkspace")
WORKSPACE = Path(_ws).expanduser()
WORKSPACE.mkdir(parents=True, exist_ok=True)

# --- Memori percakapan ---
HISTORY_TURNS = int(os.getenv("HISTORY_TURNS", "12"))
LOG_FILE = BASE_DIR / "agent.log"

SYSTEM_PROMPT = f"""Kamu adalah {AGENT_NAME}, asisten AI pribadi yang berjalan langsung di komputer pengguna.
Pengguna berbicara dalam Bahasa Indonesia melalui mikrofon, jadi teks yang kamu terima adalah hasil
transkripsi suara yang MUNGKIN mengandung salah dengar. Tebak maksud paling masuk akal; kalau benar-benar
ambigu dan aksinya berisiko, tanya dulu.

Aturan:
1. Jawabanmu akan dibacakan dengan suara. Buat singkat, natural, maksimal 2-3 kalimat.
   Jangan pakai markdown, bullet, emoji, atau simbol yang aneh saat dibaca.
2. Gunakan tool yang tersedia untuk benar-benar MENGERJAKAN perintah, bukan cuma menjelaskan caranya.
3. Boleh memakai beberapa tool berurutan untuk satu perintah.
4. Kalau sebuah tool gagal, laporkan apa adanya. Jangan mengarang keberhasilan.
5. Untuk aksi merusak (hapus file, jalankan perintah sistem), jelaskan singkat apa yang akan kamu lakukan.
"""