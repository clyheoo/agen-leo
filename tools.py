"""Kumpulan tool yang boleh dieksekusi agen di perangkat lokal.

Pola: setiap tool punya (a) skema JSON untuk Claude, (b) fungsi Python-nya.
Tambah kemampuan baru = tambah entri di TOOL_SCHEMAS + fungsi di REGISTRY.
"""
from __future__ import annotations

import datetime as dt
import os
import json
import logging
import platform
import shutil
import subprocess
import time
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
    """Buka aplikasi. Menangani 3 jenis: aplikasi Microsoft Store (lewat URI),
    aplikasi desktop biasa, dan situs web sebagai cadangan."""
    key = name.strip().lower()

    # 1. Aplikasi Store / UWP -> harus lewat protokol URI, bukan 'start nama'
    uri_apps = {
        "whatsapp": "whatsapp://",
        "wa": "whatsapp://",
        "spotify": "spotify:",
        "telegram": "tg://",
        "discord": "discord://",
        "settings": "ms-settings:",
        "pengaturan": "ms-settings:",
        "kalender": "outlookcal:",
        "mail": "outlookmail:",
    }
    if OS == "Windows" and key in uri_apps:
        try:
            os.startfile(uri_apps[key])  # type: ignore[attr-defined]
            return f"Aplikasi '{key}' dibuka."
        except Exception as exc:  # noqa: BLE001
            log.warning("URI gagal untuk %s: %s", key, exc)

    # 2. Aplikasi desktop biasa
    aliases = {
        "browser": {"Windows": "chrome", "Darwin": "Google Chrome", "Linux": "google-chrome"},
        "chrome": {"Windows": "chrome", "Darwin": "Google Chrome", "Linux": "google-chrome"},
        "edge": {"Windows": "msedge", "Darwin": "Microsoft Edge", "Linux": "microsoft-edge"},
        "vscode": {"Windows": "code", "Darwin": "Visual Studio Code", "Linux": "code"},
        "notepad": {"Windows": "notepad", "Darwin": "TextEdit", "Linux": "gedit"},
        "kalkulator": {"Windows": "calc", "Darwin": "Calculator", "Linux": "gnome-calculator"},
        "explorer": {"Windows": "explorer", "Darwin": "Finder", "Linux": "nautilus"},
        "terminal": {"Windows": "wt", "Darwin": "Terminal", "Linux": "gnome-terminal"},
        "xampp": {"Windows": r"C:\\xampp\\xampp-control.exe", "Darwin": "XAMPP", "Linux": "xampp"},
    }
    app = aliases.get(key, {}).get(OS, name)
    try:
        if OS == "Windows":
            subprocess.Popen(["cmd", "/c", "start", "", app], shell=False)
        elif OS == "Darwin":
            subprocess.Popen(["open", "-a", app])
        else:
            subprocess.Popen([app], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"Aplikasi '{app}' dijalankan."
    except Exception as exc:  # noqa: BLE001
        return f"GAGAL membuka '{app}': {exc}. Coba sebutkan nama lain."


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


def type_text(text: str, target_window: str = "") -> str:
    """Ketik teks. Kalau target_window diisi, jendela itu difokuskan dulu.

    Memakai clipboard + Ctrl+V agar huruf non-ASCII (e, aksen, emoji) tidak rusak,
    dan jauh lebih cepat daripada mengetik karakter satu per satu.
    """
    try:
        import pyautogui
        import pyperclip

        if target_window and not _focus_window(target_window):
            return f"GAGAL: jendela '{target_window}' tidak ditemukan. Buka dulu aplikasinya."

        time.sleep(0.3)
        backup = ""
        try:
            backup = pyperclip.paste()
        except Exception:  # noqa: BLE001
            pass

        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.2)

        if backup:
            try:
                pyperclip.copy(backup)
            except Exception:  # noqa: BLE001
                pass
        return f"Mengetik '{text[:40]}' ({len(text)} karakter)."
    except Exception as exc:  # noqa: BLE001
        return f"GAGAL mengetik: {exc}"


def press_hotkey(keys: str, times: int = 1, target_window: str = "") -> str:
    """keys contoh: 'ctrl+s', 'alt+tab', 'enter', 'down'. times = berapa kali ditekan."""
    try:
        import pyautogui

        if target_window and not _focus_window(target_window):
            return f"GAGAL: jendela '{target_window}' tidak ditemukan."

        combo = [k.strip().lower() for k in keys.split("+") if k.strip()]
        for _ in range(max(1, min(times, 20))):
            if len(combo) == 1:
                pyautogui.press(combo[0])
            else:
                pyautogui.hotkey(*combo)
            time.sleep(0.12)
        return f"Tombol {keys} ditekan {times} kali."
    except Exception as exc:  # noqa: BLE001
        return f"GAGAL menekan tombol: {exc}"


def focus_window(title_hint: str) -> str:
    """Aktifkan jendela aplikasi tertentu supaya perintah ketik/klik tidak salah sasaran."""
    if _focus_window(title_hint):
        return f"Jendela '{title_hint}' sekarang aktif."
    return f"GAGAL: tidak ada jendela dengan judul mengandung '{title_hint}'. Buka aplikasinya dulu."


def list_windows() -> str:
    """Lihat daftar jendela yang sedang terbuka. Berguna sebelum mengetik atau klik."""
    try:
        import pygetwindow as gw

        titles = [w.title for w in gw.getAllWindows() if (w.title or "").strip()]
        return "\n".join(f"- {t}" for t in titles[:30]) or "(tidak ada jendela terdeteksi)"
    except Exception as exc:  # noqa: BLE001
        return f"GAGAL membaca daftar jendela: {exc}"


def click_at(x: int, y: int, double: bool = False) -> str:
    """Klik di koordinat layar tertentu."""
    try:
        import pyautogui

        pyautogui.click(x, y, clicks=2 if double else 1, interval=0.1)
        return f"Klik di ({x}, {y})."
    except Exception as exc:  # noqa: BLE001
        return f"GAGAL klik: {exc}"


def wait_seconds(seconds: float) -> str:
    """Tunggu sejenak. Pakai ini setelah membuka aplikasi atau halaman berat."""
    s = max(0.2, min(float(seconds), 15))
    time.sleep(s)
    return f"Menunggu {s} detik."


def read_screen_text(target_window: str = "") -> str:
    """Baca teks dari jendela aktif dengan Ctrl+A lalu Ctrl+C, kemudian baca clipboard.

    Berguna untuk membaca isi halaman web atau dokumen yang sedang dibuka.
    """
    try:
        import pyautogui
        import pyperclip

        if target_window and not _focus_window(target_window):
            return f"GAGAL: jendela '{target_window}' tidak ditemukan."

        time.sleep(0.3)
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.2)
        pyautogui.hotkey("ctrl", "c")
        time.sleep(0.5)
        pyautogui.click()  # batalkan seleksi
        text = pyperclip.paste() or ""
        text = " ".join(text.split())
        if not text:
            return "Tidak ada teks yang bisa dibaca dari jendela itu."
        return text[:6000] + ("... (dipotong)" if len(text) > 6000 else "")
    except Exception as exc:  # noqa: BLE001
        return f"GAGAL membaca layar: {exc}"


def fetch_web_page(url: str) -> str:
    """Ambil dan baca isi teks sebuah halaman web LANGSUNG (tanpa browser).

    Jauh lebih akurat daripada read_screen_text untuk merangkum artikel.
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        import re as _re
        import urllib.request

        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read(1_500_000).decode("utf-8", errors="replace")

        raw = _re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", raw)
        text = _re.sub(r"(?s)<[^>]+>", " ", raw)
        text = _re.sub(r"&nbsp;?", " ", text)
        text = " ".join(text.split())
        if not text:
            return "Halaman terbuka tapi tidak ada teks yang terbaca."
        return text[:6000] + ("... (dipotong)" if len(text) > 6000 else "")
    except Exception as exc:  # noqa: BLE001
        return f"GAGAL membuka halaman: {exc}"


def play_youtube_video(query: str) -> str:
    """Cari di YouTube lalu LANGSUNG PUTAR video pertama (bukan cuma halaman hasil)."""
    try:
        import re as _re
        import urllib.request

        search = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
        req = urllib.request.Request(search, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read(900_000).decode("utf-8", errors="replace")

        ids = _re.findall(r'"videoId":"([\w-]{11})"', html)
        if not ids:
            webbrowser.open(search)
            return f"Video tidak terdeteksi, saya buka halaman pencarian '{query}'."

        url = f"https://www.youtube.com/watch?v={ids[0]}"
        webbrowser.open(url)
        return f"Memutar video pertama untuk '{query}': {url}"
    except Exception as exc:  # noqa: BLE001
        webbrowser.open(f"https://www.youtube.com/results?search_query={quote_plus(query)}")
        return f"Gagal memilih video ({exc}), halaman pencarian dibuka."


def whatsapp_send(contact: str, message: str) -> str:
    """Kirim pesan WhatsApp: fokus aplikasi, cari kontak, ketik, kirim."""
    try:
        import pyautogui

        if not _focus_window("whatsapp"):
            open_application("whatsapp")
            time.sleep(4)
            if not _focus_window("whatsapp"):
                return "GAGAL: aplikasi WhatsApp tidak terbuka."

        time.sleep(0.8)
        pyautogui.hotkey("ctrl", "f")       # kotak pencarian kontak
        time.sleep(0.6)
        type_text(contact)
        time.sleep(1.5)
        pyautogui.press("down")             # pilih hasil pertama
        time.sleep(0.3)
        pyautogui.press("enter")
        time.sleep(1.2)
        type_text(message)
        time.sleep(0.4)
        pyautogui.press("enter")
        return f"Pesan '{message[:40]}' dikirim ke '{contact}'. Mohon dicek layarnya."
    except Exception as exc:  # noqa: BLE001
        return f"GAGAL mengirim pesan WhatsApp: {exc}"


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


def _win32_force_focus(hwnd: int) -> bool:
    """Paksa jendela ke depan lewat Win32 API.

    pygetwindow.activate() sering gagal di Windows karena OS melarang proses
    lain 'mencuri' fokus. Trik AttachThreadInput di bawah adalah cara resmi
    untuk mengatasinya.
    """
    if OS != "Windows":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        u32 = ctypes.windll.user32
        SW_RESTORE = 9

        if u32.IsIconic(hwnd):
            u32.ShowWindow(hwnd, SW_RESTORE)

        fg = u32.GetForegroundWindow()
        cur_thread = ctypes.windll.kernel32.GetCurrentThreadId()
        fg_thread = u32.GetWindowThreadProcessId(fg, None)
        tgt_thread = u32.GetWindowThreadProcessId(hwnd, None)

        for t in {fg_thread, tgt_thread}:
            if t and t != cur_thread:
                u32.AttachThreadInput(cur_thread, t, True)
        try:
            u32.BringWindowToTop(hwnd)
            u32.SetForegroundWindow(hwnd)
            u32.SetActiveWindow(hwnd)
        finally:
            for t in {fg_thread, tgt_thread}:
                if t and t != cur_thread:
                    u32.AttachThreadInput(cur_thread, t, False)

        time.sleep(0.35)
        return u32.GetForegroundWindow() == hwnd
    except Exception as exc:  # noqa: BLE001
        log.warning("Win32 focus gagal: %s", exc)
        return False


def _active_title() -> str:
    try:
        import pygetwindow as gw

        return (gw.getActiveWindowTitle() or "").lower()
    except Exception:  # noqa: BLE001
        return ""


def _focus_window(title_hint: str) -> bool:
    """Aktifkan jendela yang judulnya mengandung title_hint. Dua strategi bertingkat."""
    hint = title_hint.lower().strip()
    if not hint:
        return False

    try:
        import pygetwindow as gw

        matches = [
            w for w in gw.getAllWindows()
            if (w.title or "").strip() and hint in w.title.lower()
        ]
    except Exception as exc:  # noqa: BLE001
        log.warning("Tidak bisa membaca daftar jendela: %s", exc)
        return False

    if not matches:
        log.info("Jendela '%s' tidak ditemukan.", hint)
        return False

    for w in matches:
        # Strategi 1: cara bawaan pygetwindow
        try:
            if w.isMinimized:
                w.restore()
                time.sleep(0.3)
            w.activate()
            time.sleep(0.4)
            if hint in _active_title():
                return True
        except Exception:  # noqa: BLE001
            pass

        # Strategi 2: paksa lewat Win32
        hwnd = getattr(w, "_hWnd", None)
        if hwnd and _win32_force_focus(hwnd):
            return True
        if hint in _active_title():
            return True

    log.warning("Semua strategi fokus gagal untuk '%s'.", hint)
    return False


def navigate_current_tab(url: str, browser: str = "chrome") -> str:
    """Buka alamat DI TAB YANG SEDANG AKTIF, bukan tab baru."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    hint = {"chrome": "chrome", "edge": "edge", "firefox": "firefox"}.get(
        browser.strip().lower(), browser
    )
    if not _focus_window(hint):
        webbrowser.open(url)
        return f"Jendela {browser} tidak ditemukan, jadi saya buka di tab baru: {url}"

    try:
        import pyautogui

        pyautogui.hotkey("ctrl", "l")     # fokus ke address bar
        time.sleep(0.2)
        pyautogui.write(url, interval=0.005)
        pyautogui.press("enter")
        return f"Tab aktif dialihkan ke {url}"
    except Exception as exc:  # noqa: BLE001
        return f"GAGAL mengarahkan tab aktif: {exc}"


def search_youtube_current_tab(query: str) -> str:
    """Cari di YouTube menggunakan tab yang sedang aktif."""
    return navigate_current_tab(
        f"https://www.youtube.com/results?search_query={quote_plus(query)}"
    )


# ====================================================================== #
# Registry + skema untuk Claude
# ====================================================================== #
REGISTRY = {
    "open_application": open_application,
    "open_url": open_url,
    "navigate_current_tab": navigate_current_tab,
    "search_youtube_current_tab": search_youtube_current_tab,
    "web_search": web_search,
    "play_youtube": play_youtube,
    "get_datetime": get_datetime,
    "system_info": system_info,
    "control_media": control_media,
    "type_text": type_text,
    "press_hotkey": press_hotkey,
    "focus_window": focus_window,
    "list_windows": list_windows,
    "click_at": click_at,
    "wait_seconds": wait_seconds,
    "read_screen_text": read_screen_text,
    "fetch_web_page": fetch_web_page,
    "play_youtube_video": play_youtube_video,
    "whatsapp_send": whatsapp_send,
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
    _schema("navigate_current_tab",
            "WAJIB dipakai kalau pengguna sudah punya browser terbuka dan ingin berpindah halaman "
            "TANPA membuka tab baru. Contoh: 'buka video lain', 'cari yang ini saja', 'ganti halaman'.",
            {"url": {"type": "string"},
             "browser": {"type": "string", "description": "chrome (default), edge, atau firefox"}},
            ["url"]),
    _schema("search_youtube_current_tab",
            "Mencari di YouTube memakai tab yang SEDANG AKTIF, bukan tab baru. "
            "Pakai ini kalau YouTube sudah terbuka dan pengguna ingin mencari hal lain.",
            {"query": {"type": "string"}}, ["query"]),
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
    _schema("type_text",
            "Mengetik teks ke aplikasi. SELALU isi target_window kalau tahu aplikasinya, "
            "supaya teks tidak salah masuk ke jendela lain.",
            {"text": {"type": "string"},
             "target_window": {"type": "string", "description": "sebagian judul jendela, mis. 'whatsapp', 'chrome'"}},
            ["text"]),
    _schema("press_hotkey",
            "Menekan tombol atau kombinasi, mis. 'enter', 'ctrl+s', 'down'. times = berapa kali.",
            {"keys": {"type": "string"},
             "times": {"type": "integer"},
             "target_window": {"type": "string"}},
            ["keys"]),
    _schema("focus_window",
            "Mengaktifkan jendela aplikasi. WAJIB dipanggil sebelum mengetik atau klik "
            "kalau aplikasinya belum tentu di depan.",
            {"title_hint": {"type": "string"}}, ["title_hint"]),
    _schema("list_windows",
            "Melihat daftar jendela yang sedang terbuka beserta judulnya. "
            "Pakai ini untuk memastikan aplikasi yang dimaksud memang sudah terbuka."),
    _schema("click_at", "Klik mouse di koordinat layar tertentu.",
            {"x": {"type": "integer"}, "y": {"type": "integer"},
             "double": {"type": "boolean"}}, ["x", "y"]),
    _schema("wait_seconds",
            "Menunggu beberapa detik. Pakai setelah membuka aplikasi atau halaman berat "
            "sebelum mengetik, agar tidak salah sasaran.",
            {"seconds": {"type": "number"}}, ["seconds"]),
    _schema("read_screen_text",
            "MEMBACA isi teks dari jendela yang sedang terbuka (halaman web, dokumen). "
            "Pakai kalau pengguna bertanya 'apa isi halaman ini' atau minta dirangkum.",
            {"target_window": {"type": "string"}}),
    _schema("fetch_web_page",
            "Mengambil dan membaca isi sebuah alamat web secara langsung tanpa browser. "
            "Lebih akurat daripada read_screen_text untuk merangkum artikel.",
            {"url": {"type": "string"}}, ["url"]),
    _schema("play_youtube_video",
            "Mencari di YouTube lalu LANGSUNG MEMUTAR video pertama. "
            "Pakai ini kalau pengguna bilang 'putarkan', 'tontonkan', 'mainkan video'.",
            {"query": {"type": "string"}}, ["query"]),
    _schema("whatsapp_send",
            "Mengirim pesan WhatsApp ke sebuah kontak lewat aplikasi desktop.",
            {"contact": {"type": "string"}, "message": {"type": "string"}},
            ["contact", "message"]),
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