"""Kumpulan tool yang boleh dieksekusi agen di perangkat lokal.

Pola: setiap tool punya (a) skema JSON untuk Claude, (b) fungsi Python-nya.
Tambah kemampuan baru = tambah entri di TOOL_SCHEMAS + fungsi di REGISTRY.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import platform
import shutil
import subprocess
import threading
import webbrowser
from pathlib import Path
from urllib.parse import quote_plus

import config

log = logging.getLogger("tools")
OS = platform.system()  # Windows | Darwin | Linux


# ====================================================================== #
# Helper
# ====================================================================== #
def _safe_path(rel: str) -> Path:
    """Cegah path traversal: semua operasi file dikunci di dalam WORKSPACE."""
    target = (config.WORKSPACE / rel).expanduser().resolve()
    root = config.WORKSPACE.resolve()
    if root != target and root not in target.parents:
        raise PermissionError(f"Akses ditolak. File harus berada di dalam {root}")
    return target


def _confirm(question: str) -> bool:
    if not config.CONFIRM_RISKY_ACTIONS:
        return True
    import tts

    tts.say(question + " Ketik y lalu Enter untuk setuju.")
    try:
        return input("Konfirmasi (y/n): ").strip().lower() in ("y", "ya", "yes")
    except EOFError:
        return False


# ====================================================================== #
# Implementasi tool
# ====================================================================== #
def open_application(name: str) -> str:
    aliases = {
        "browser": {"Windows": "chrome", "Darwin": "Google Chrome", "Linux": "google-chrome"},
        "chrome": {"Windows": "chrome", "Darwin": "Google Chrome", "Linux": "google-chrome"},
        "vscode": {"Windows": "code", "Darwin": "Visual Studio Code", "Linux": "code"},
        "notepad": {"Windows": "notepad", "Darwin": "TextEdit", "Linux": "gedit"},
        "kalkulator": {"Windows": "calc", "Darwin": "Calculator", "Linux": "gnome-calculator"},
        "explorer": {"Windows": "explorer", "Darwin": "Finder", "Linux": "nautilus"},
        "terminal": {"Windows": "wt", "Darwin": "Terminal", "Linux": "gnome-terminal"},
        "spotify": {"Windows": "spotify", "Darwin": "Spotify", "Linux": "spotify"},
    }
    app = aliases.get(name.strip().lower(), {}).get(OS, name)
    try:
        if OS == "Windows":
            subprocess.Popen(["cmd", "/c", "start", "", app], shell=False)
        elif OS == "Darwin":
            subprocess.Popen(["open", "-a", app])
        else:
            subprocess.Popen([app], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"Aplikasi '{app}' dijalankan."
    except Exception as exc:  # noqa: BLE001
        return f"GAGAL membuka '{app}': {exc}"


def open_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    webbrowser.open(url)
    return f"Membuka {url}"


def web_search(query: str) -> str:
    webbrowser.open(f"https://www.google.com/search?q={quote_plus(query)}")
    return f"Hasil pencarian '{query}' dibuka di browser."


def play_youtube(query: str) -> str:
    webbrowser.open(f"https://www.youtube.com/results?search_query={quote_plus(query)}")
    return f"YouTube dibuka untuk '{query}'."


def get_datetime() -> str:
    now = dt.datetime.now()
    hari = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"][now.weekday()]
    return f"{hari}, {now.strftime('%d-%m-%Y %H:%M:%S')}"


def system_info() -> str:
    info = {
        "os": f"{platform.system()} {platform.release()}",
        "host": platform.node(),
        "cpu": platform.processor() or platform.machine(),
    }
    try:
        import psutil

        info["cpu_percent"] = f"{psutil.cpu_percent(interval=0.4)}%"
        info["ram_percent"] = f"{psutil.virtual_memory().percent}%"
        bat = psutil.sensors_battery()
        if bat:
            info["baterai"] = f"{int(bat.percent)}%" + (" (mengisi)" if bat.power_plugged else "")
    except Exception:  # noqa: BLE001
        pass
    total, used, free = shutil.disk_usage(Path.home())
    info["disk_kosong"] = f"{free // 2**30} GB dari {total // 2**30} GB"
    return json.dumps(info, ensure_ascii=False)


def control_media(action: str) -> str:
    """action: playpause | next | prev | volume_up | volume_down | mute"""
    keymap = {
        "playpause": "playpause",
        "next": "nexttrack",
        "prev": "prevtrack",
        "volume_up": "volumeup",
        "volume_down": "volumedown",
        "mute": "volumemute",
    }
    key = keymap.get(action)
    if not key:
        return f"Aksi '{action}' tidak dikenal."
    try:
        import pyautogui

        repeat = 5 if action.startswith("volume_") else 1
        for _ in range(repeat):
            pyautogui.press(key)
        return f"Aksi media '{action}' dijalankan."
    except Exception as exc:  # noqa: BLE001
        return f"GAGAL kontrol media: {exc}"


def type_text(text: str) -> str:
    try:
        import pyautogui

        pyautogui.write(text, interval=0.01)
        return f"Mengetik {len(text)} karakter di jendela aktif."
    except Exception as exc:  # noqa: BLE001
        return f"GAGAL mengetik: {exc}"


def press_hotkey(keys: str) -> str:
    """keys contoh: 'ctrl+s', 'alt+tab', 'win+d'"""
    try:
        import pyautogui

        pyautogui.hotkey(*[k.strip().lower() for k in keys.split("+")])
        return f"Hotkey {keys} ditekan."
    except Exception as exc:  # noqa: BLE001
        return f"GAGAL menekan hotkey: {exc}"


def take_screenshot(filename: str = "") -> str:
    try:
        import pyautogui

        name = filename or f"screenshot_{dt.datetime.now():%Y%m%d_%H%M%S}.png"
        path = _safe_path(name)
        pyautogui.screenshot().save(path)
        return f"Screenshot disimpan di {path}"
    except Exception as exc:  # noqa: BLE001
        return f"GAGAL screenshot: {exc}"


def list_files(subdir: str = "") -> str:
    path = _safe_path(subdir)
    if not path.exists():
        return f"Folder {path} tidak ada."
    items = [f"{'[D] ' if p.is_dir() else '[F] '}{p.name}" for p in sorted(path.iterdir())][:100]
    return "\n".join(items) or "(folder kosong)"


def read_file(filename: str) -> str:
    path = _safe_path(filename)
    if not path.is_file():
        return f"File {path} tidak ditemukan."
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[:8000] + ("\n...(dipotong)" if len(text) > 8000 else "")


def write_file(filename: str, content: str, append: bool = False) -> str:
    path = _safe_path(filename)
    if path.exists() and not append and not _confirm(f"File {path.name} sudah ada dan akan ditimpa. Lanjut?"):
        return "Dibatalkan oleh pengguna."
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a" if append else "w", encoding="utf-8") as fh:
        fh.write(content)
    return f"Tersimpan di {path}"


def set_timer(seconds: int, message: str = "Waktunya habis.") -> str:
    def _fire() -> None:
        import tts

        tts.say(message)

    threading.Timer(max(1, seconds), _fire).start()
    return f"Pengingat diset {seconds} detik lagi."


def run_shell(command: str) -> str:
    if not config.ALLOW_SHELL:
        return "DITOLAK: eksekusi shell dimatikan. Set ALLOW_SHELL=true di .env bila diperlukan."
    if not _confirm(f"Saya akan menjalankan perintah: {command}. Setuju?"):
        return "Dibatalkan oleh pengguna."
    try:
        proc = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=60,
            cwd=str(config.WORKSPACE),
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        return f"exit={proc.returncode}\n{out[:4000]}"
    except subprocess.TimeoutExpired:
        return "GAGAL: perintah melebihi 60 detik."
    except Exception as exc:  # noqa: BLE001
        return f"GAGAL: {exc}"


# ====================================================================== #
# Registry + skema untuk Claude
# ====================================================================== #
REGISTRY = {
    "open_application": open_application,
    "open_url": open_url,
    "web_search": web_search,
    "play_youtube": play_youtube,
    "get_datetime": get_datetime,
    "system_info": system_info,
    "control_media": control_media,
    "type_text": type_text,
    "press_hotkey": press_hotkey,
    "take_screenshot": take_screenshot,
    "list_files": list_files,
    "read_file": read_file,
    "write_file": write_file,
    "set_timer": set_timer,
    "run_shell": run_shell,
}


def _schema(name, desc, props=None, required=None):
    return {
        "name": name,
        "description": desc,
        "input_schema": {
            "type": "object",
            "properties": props or {},
            "required": required or [],
        },
    }


TOOL_SCHEMAS = [
    _schema("open_application", "Membuka aplikasi di komputer pengguna.",
            {"name": {"type": "string", "description": "Nama aplikasi, mis. chrome, vscode, spotify, kalkulator"}},
            ["name"]),
    _schema("open_url", "Membuka sebuah alamat web di browser.",
            {"url": {"type": "string"}}, ["url"]),
    _schema("web_search", "Mencari sesuatu di Google dan membukanya di browser.",
            {"query": {"type": "string"}}, ["query"]),
    _schema("play_youtube", "Membuka YouTube untuk memutar lagu/video tertentu.",
            {"query": {"type": "string"}}, ["query"]),
    _schema("get_datetime", "Mengambil tanggal dan jam saat ini di perangkat pengguna."),
    _schema("system_info", "Status perangkat: OS, CPU, RAM, baterai, sisa disk."),
    _schema("control_media", "Kontrol pemutaran media dan volume sistem.",
            {"action": {"type": "string",
                        "enum": ["playpause", "next", "prev", "volume_up", "volume_down", "mute"]}},
            ["action"]),
    _schema("type_text", "Mengetikkan teks ke jendela/aplikasi yang sedang aktif.",
            {"text": {"type": "string"}}, ["text"]),
    _schema("press_hotkey", "Menekan kombinasi tombol keyboard, mis. 'ctrl+s' atau 'alt+tab'.",
            {"keys": {"type": "string"}}, ["keys"]),
    _schema("take_screenshot", "Mengambil tangkapan layar dan menyimpannya ke workspace.",
            {"filename": {"type": "string", "description": "Opsional, mis. layar.png"}}),
    _schema("list_files", "Melihat isi folder workspace agen.",
            {"subdir": {"type": "string", "description": "Opsional, subfolder relatif"}}),
    _schema("read_file", "Membaca isi file teks di dalam workspace agen.",
            {"filename": {"type": "string"}}, ["filename"]),
    _schema("write_file", "Menulis atau menambah isi file teks di workspace agen (catatan, draf, dsb).",
            {"filename": {"type": "string"},
             "content": {"type": "string"},
             "append": {"type": "boolean", "description": "true untuk menambah di akhir file"}},
            ["filename", "content"]),
    _schema("set_timer", "Membuat pengingat/timer yang akan diucapkan setelah sekian detik.",
            {"seconds": {"type": "integer"}, "message": {"type": "string"}}, ["seconds"]),
    _schema("run_shell", "Menjalankan perintah shell/terminal. Berisiko, butuh izin pengguna.",
            {"command": {"type": "string"}}, ["command"]),
]


def execute(name: str, args: dict) -> str:
    fn = REGISTRY.get(name)
    if fn is None:
        return f"Tool '{name}' tidak tersedia."
    try:
        log.info("TOOL %s(%s)", name, args)
        return str(fn(**args))
    except TypeError as exc:
        return f"Parameter salah untuk {name}: {exc}"
    except Exception as exc:  # noqa: BLE001
        log.exception("Tool error")
        return f"GAGAL menjalankan {name}: {exc}"