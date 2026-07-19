"""Uji setiap tool SECARA LANGSUNG, tanpa melibatkan model AI sama sekali.

Tujuannya memisahkan dua kemungkinan penyebab:
  A. Tool-nya sendiri rusak di komputer ini  -> terlihat di sini
  B. Tool-nya baik, tapi model salah memilih -> di sini semua lolos

Jalankan:  python diagnosa.py
"""
from __future__ import annotations

import time

import tools

OK, FAIL = "[ OK ]", "[GAGAL]"


def cek(judul: str, hasil: str, sukses_jika_tidak_ada: str = "GAGAL") -> bool:
    ok = sukses_jika_tidak_ada not in hasil
    print(f"{OK if ok else FAIL} {judul}")
    print(f"        -> {hasil[:160]}")
    return ok


def main() -> None:
    print("=" * 62)
    print(" DIAGNOSA TOOL — jangan sentuh mouse/keyboard selama proses ini")
    print("=" * 62)
    skor = []

    # --- 1. Yang tidak menyentuh UI -----------------------------------
    print("\n--- 1. Dasar (tanpa UI) ---")
    skor.append(cek("get_datetime", tools.get_datetime()))
    skor.append(cek("system_info", tools.system_info()))
    skor.append(cek("write_file", tools.write_file("uji_leo.txt", "halo dari Leo")))
    skor.append(cek("read_file", tools.read_file("uji_leo.txt")))

    # --- 2. Internet ---------------------------------------------------
    print("\n--- 2. Internet ---")
    skor.append(cek("fetch_web_page", tools.fetch_web_page("https://example.com")))

    # --- 3. Jendela ----------------------------------------------------
    print("\n--- 3. Deteksi jendela ---")
    daftar = tools.list_windows()
    skor.append(cek("list_windows", daftar))
    print("\n  Jendela yang terdeteksi:")
    for baris in daftar.splitlines()[:12]:
        print("   ", baris)

    # --- 4. Fokus + ketik ---------------------------------------------
    print("\n--- 4. Fokus & ketik (butuh Notepad) ---")
    print("  Membuka Notepad...")
    tools.open_application("notepad")
    time.sleep(3)

    skor.append(cek("focus_window(notepad)", tools.focus_window("notepad")))
    time.sleep(0.5)
    skor.append(cek("type_text ke Notepad",
                    tools.type_text("Tes dari Leo 123", target_window="notepad")))
    time.sleep(0.5)
    skor.append(cek("press_hotkey enter",
                    tools.press_hotkey("enter", target_window="notepad")))

    print("\n  >> LIHAT NOTEPAD: apakah tulisan 'Tes dari Leo 123' muncul di sana?")

    # --- 5. YouTube ----------------------------------------------------
    print("\n--- 5. YouTube ---")
    skor.append(cek("play_youtube_video", tools.play_youtube_video("lofi hip hop")))
    print("  >> LIHAT BROWSER: apakah video langsung terputar (bukan halaman hasil)?")
    time.sleep(4)

    skor.append(cek("navigate_current_tab",
                    tools.navigate_current_tab("https://www.google.com")))
    print("  >> LIHAT BROWSER: apakah tab yang SAMA berpindah ke Google?")

    # --- Ringkasan -----------------------------------------------------
    lolos = sum(skor)
    print("\n" + "=" * 62)
    print(f" HASIL: {lolos} dari {len(skor)} tool lolos")
    print("=" * 62)
    if lolos < len(skor):
        print("\nTool yang GAGAL di atas adalah masalah di komputer ini,")
        print("bukan masalah kecerdasan model. Kirim baris GAGAL-nya untuk dianalisis.")
    else:
        print("\nSemua tool berfungsi. Kalau agen masih salah saat dipakai,")
        print("berarti masalahnya di PEMILIHAN tool oleh model, bukan di kodenya.")


if __name__ == "__main__":
    main()