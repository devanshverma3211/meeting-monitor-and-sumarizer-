#!/usr/bin/env python3
"""
Meeting Monitor — Desktop GUI
=============================
A friendly toggle-button app to start/stop Meeting Monitor
without ever touching a terminal.

Double-click  →  Start Monitor.bat  →  this window appears.
"""

import tkinter as tk
from tkinter import messagebox
import subprocess
import sys
import threading
import queue
import json
import os
from pathlib import Path
from datetime import datetime

# Optional tray support (needs pystray + Pillow from requirements.txt)
try:
    from PIL import Image, ImageDraw
    import pystray
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False

SCRIPT_DIR = Path(__file__).parent
TRIGGER_FILE = SCRIPT_DIR / ".send_summary_now"

# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------
BG        = "#1a1a2e"
CARD      = "#16213e"
CARD2     = "#1e1e3a"
ON_GREEN  = "#00c96a"
ON_HOVER  = "#00a855"
OFF_RED   = "#e05252"
OFF_HOVER = "#c04040"
IDLE      = "#4a4a6a"
TEXT      = "#e2e2f0"
SUBTEXT   = "#7878a0"
LOG_BG    = "#0d0d1e"
LOG_FG    = "#7fffb0"
ACCENT    = "#5e5ef0"


# ---------------------------------------------------------------------------
# Rounded button helper (pure tkinter, no extra libs)
# ---------------------------------------------------------------------------
class RoundedButton(tk.Canvas):
    def __init__(self, parent, text, command, width=200, height=70,
                 radius=16, bg_color=ON_GREEN, hover_color=ON_HOVER,
                 fg_color="white", font_size=14, **kwargs):
        super().__init__(parent, width=width, height=height,
                         bg=BG, highlightthickness=0, **kwargs)
        self.command    = command
        self.bg_color   = bg_color
        self.hover_color= hover_color
        self.fg_color   = fg_color
        self.radius     = radius
        self.width      = width
        self.height     = height
        self.font_size  = font_size
        self._text      = text

        self._draw(bg_color)
        self.bind("<Enter>",    lambda e: self._draw(hover_color))
        self.bind("<Leave>",    lambda e: self._draw(self.bg_color))
        self.bind("<Button-1>", lambda e: command())

    def _draw(self, color):
        self.delete("all")
        r = self.radius
        w, h = self.width, self.height
        # Rounded rectangle via polygon
        self.create_polygon(
            r, 0,  w-r, 0,  w, r,  w, h-r,  w-r, h,  r, h,  0, h-r,  0, r,
            smooth=True, fill=color, outline=""
        )
        self.create_text(w//2, h//2, text=self._text,
                         fill=self.fg_color,
                         font=("Segoe UI", self.font_size, "bold"))

    def update_text(self, text, bg_color, hover_color):
        self._text       = text
        self.bg_color    = bg_color
        self.hover_color = hover_color
        self._draw(bg_color)


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------
class MeetingMonitorApp:

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Meeting Monitor")
        self.root.geometry("520x620")
        self.root.resizable(False, False)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Try to set a window icon (green circle)
        self._set_icon()

        self.process         = None
        self.running         = False
        self.recording_count = 0
        self.log_queue       = queue.Queue()
        self._tray_icon      = None

        self._build_ui()
        self._load_config_display()
        self._poll_logs()

    # ------------------------------------------------------------------
    # Icon
    # ------------------------------------------------------------------
    def _set_icon(self):
        try:
            from PIL import Image, ImageDraw, ImageTk
            img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            d   = ImageDraw.Draw(img)
            d.ellipse([4, 4, 60, 60], fill=(0, 201, 106))
            self._icon_img = ImageTk.PhotoImage(img)
            self.root.iconphoto(True, self._icon_img)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self):

        # ── Header ──────────────────────────────────────────────────────
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=24, pady=(22, 0))

        tk.Label(header, text="🎙️  Meeting Monitor",
                 bg=BG, fg=TEXT,
                 font=("Segoe UI", 18, "bold")).pack(side="left")

        self.status_dot = tk.Label(header, text="⬤  OFFLINE",
                                    bg=BG, fg=IDLE,
                                    font=("Segoe UI", 9, "bold"))
        self.status_dot.pack(side="right", pady=4)

        # Divider
        tk.Frame(self.root, bg="#252545", height=1).pack(fill="x", padx=24, pady=14)

        # ── Toggle button ────────────────────────────────────────────────
        btn_frame = tk.Frame(self.root, bg=BG)
        btn_frame.pack(pady=6)

        self.toggle_btn = RoundedButton(
            btn_frame,
            text="▶  START MONITORING",
            command=self.toggle,
            width=280, height=64,
            radius=18,
            bg_color=ON_GREEN, hover_color=ON_HOVER,
            font_size=13,
        )
        self.toggle_btn.pack()

        self.hint_label = tk.Label(
            self.root,
            text="Click to start — Teams calls will be recorded automatically",
            bg=BG, fg=SUBTEXT, font=("Segoe UI", 9),
            wraplength=440, justify="center"
        )
        self.hint_label.pack(pady=(10, 0))

        # ── Info cards ───────────────────────────────────────────────────
        cards = tk.Frame(self.root, bg=BG)
        cards.pack(fill="x", padx=24, pady=18)

        self.card_recordings = self._card(cards, "📁 Recordings Today", "0")
        self.card_recordings.pack(side="left", expand=True, fill="x", padx=(0, 8))

        self.card_summary = self._card(cards, "⏰ Daily Summary At", "—")
        self.card_summary.pack(side="left", expand=True, fill="x", padx=(0, 8))

        self.card_status = self._card(cards, "📡 Status", "Idle")
        self.card_status.pack(side="left", expand=True, fill="x")

        # ── Live log ─────────────────────────────────────────────────────
        log_header = tk.Frame(self.root, bg=BG)
        log_header.pack(fill="x", padx=24, pady=(4, 4))

        tk.Label(log_header, text="Live Log",
                 bg=BG, fg=SUBTEXT,
                 font=("Segoe UI", 9, "bold")).pack(side="left")

        tk.Button(log_header, text="Clear",
                  bg=BG, fg=SUBTEXT,
                  font=("Segoe UI", 8), relief="flat",
                  cursor="hand2", bd=0,
                  activebackground=BG, activeforeground=TEXT,
                  command=self._clear_log).pack(side="right")

        self.log_box = tk.Text(
            self.root,
            bg=LOG_BG, fg=LOG_FG,
            font=("Consolas", 8),
            height=11,
            relief="flat",
            state="disabled",
            wrap="word",
            padx=10, pady=8,
            insertbackground=LOG_FG,
        )
        self.log_box.pack(fill="x", padx=24, pady=(0, 0))

        # ── Bottom actions ────────────────────────────────────────────────
        actions = tk.Frame(self.root, bg=BG)
        actions.pack(fill="x", padx=24, pady=14)

        self._action_btn(actions, "📧  Send Summary Now",
                         self._send_now).pack(side="left")

        self._action_btn(actions, "⚙  Open Config",
                         self._open_config).pack(side="left", padx=8)

        if TRAY_AVAILABLE:
            self._action_btn(actions, "⬇  Minimise to Tray",
                             self._minimize_to_tray).pack(side="right")

    # -- small helpers ---------------------------------------------------

    def _card(self, parent, label, value):
        frame = tk.Frame(parent, bg=CARD, padx=12, pady=10)
        tk.Label(frame, text=label,
                 bg=CARD, fg=SUBTEXT,
                 font=("Segoe UI", 8)).pack(anchor="w")
        val = tk.Label(frame, text=value,
                       bg=CARD, fg=TEXT,
                       font=("Segoe UI", 14, "bold"))
        val.pack(anchor="w")
        frame._val = val          # store reference on the frame
        return frame

    def _set_card(self, card_frame, text):
        card_frame._val.config(text=text)

    def _action_btn(self, parent, text, cmd):
        return tk.Button(
            parent, text=text,
            command=cmd,
            bg=CARD2, fg=TEXT,
            font=("Segoe UI", 9),
            relief="flat", cursor="hand2",
            padx=12, pady=7, bd=0,
            activebackground=ACCENT,
            activeforeground="white",
        )

    # ------------------------------------------------------------------
    # Config display
    # ------------------------------------------------------------------
    def _load_config_display(self):
        cfg_path = SCRIPT_DIR / "config.json"
        if not cfg_path.exists():
            self._set_card(self.card_summary, "No config.json")
            self._append_log("⚠  config.json not found. Please add it to the app folder.")
            return
        try:
            with open(cfg_path, encoding="utf-8") as f:
                cfg = json.load(f)
            self._set_card(self.card_summary, cfg.get("summary_time", "18:00"))
        except Exception as e:
            self._set_card(self.card_summary, "Error")
            self._append_log(f"⚠  Could not read config.json: {e}")

    # ------------------------------------------------------------------
    # Toggle
    # ------------------------------------------------------------------
    def toggle(self):
        if self.running:
            self._stop()
        else:
            self._start()

    def _start(self):
        main_py = SCRIPT_DIR / "main.py"
        if not main_py.exists():
            messagebox.showerror("File missing",
                                 "main.py not found in the app folder.\n"
                                 "Make sure all files are in the same folder.")
            return

        try:
            self.process = subprocess.Popen(
                [sys.executable, str(main_py)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=SCRIPT_DIR,
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
        except Exception as e:
            messagebox.showerror("Start error", str(e))
            return

        self.running = True
        self.recording_count = 0
        self._set_card(self.card_recordings, "0")
        self._update_ui(running=True)
        threading.Thread(target=self._read_output, daemon=True).start()
        self._append_log("▶  Monitor started. Waiting for a Teams call…")

    def _stop(self):
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None

        self.running = False
        self._update_ui(running=False)
        self._append_log("■  Monitor stopped.")

    # ------------------------------------------------------------------
    # UI state update
    # ------------------------------------------------------------------
    def _update_ui(self, running: bool):
        if running:
            self.toggle_btn.update_text(
                "■  STOP MONITORING", OFF_RED, OFF_HOVER)
            self.status_dot.config(text="⬤  ACTIVE", fg=ON_GREEN)
            self.hint_label.config(
                text="Monitoring is ON — Teams calls will be recorded automatically")
            self._set_card(self.card_status, "Active")
        else:
            self.toggle_btn.update_text(
                "▶  START MONITORING", ON_GREEN, ON_HOVER)
            self.status_dot.config(text="⬤  OFFLINE", fg=IDLE)
            self.hint_label.config(
                text="Click to start — Teams calls will be recorded automatically")
            self._set_card(self.card_status, "Idle")

        # Update tray icon if visible
        if self._tray_icon:
            try:
                self._tray_icon.icon = self._make_tray_image()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Log reader (background thread → queue → main thread)
    # ------------------------------------------------------------------
    def _read_output(self):
        for line in self.process.stdout:
            line = line.rstrip()
            if not line:
                continue
            self.log_queue.put(line)

            # Count saved recordings
            if "Recording saved" in line:
                self.recording_count += 1
                count = self.recording_count
                self.root.after(0, lambda c=count:
                                self._set_card(self.card_recordings, str(c)))

            # Reflect recording status in card
            if "Recording started" in line:
                self.root.after(0, lambda:
                                self._set_card(self.card_status, "🔴 Recording"))
            elif "Recording saved" in line or "Monitoring" in line:
                self.root.after(0, lambda:
                                self._set_card(self.card_status, "Active"))
            elif "Summary" in line and "sent" in line:
                self.root.after(0, lambda:
                                self._set_card(self.card_status, "✉ Email sent"))

        # Process exited
        self.root.after(0, self._process_exited)

    def _process_exited(self):
        if self.running:        # unexpected exit
            self.running = False
            self._update_ui(running=False)
            self._append_log(
                "⚠  Monitor stopped unexpectedly — see log for details.")

    def _poll_logs(self):
        try:
            while True:
                self._append_log(self.log_queue.get_nowait())
        except Exception:
            pass
        self.root.after(150, self._poll_logs)

    def _append_log(self, text: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_box.config(state="normal")
        self.log_box.insert("end", f"[{ts}]  {text}\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    def _clear_log(self):
        self.log_box.config(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.config(state="disabled")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _send_now(self):
        if not self.running:
            messagebox.showinfo("Not running",
                                "Start the monitor first, then use this button "
                                "to trigger an early summary email.")
            return
        try:
            TRIGGER_FILE.touch()
            self._append_log("📧  Manual summary triggered — email will send shortly.")
        except Exception as e:
            self._append_log(f"⚠  Could not write trigger file: {e}")

    def _open_config(self):
        cfg = SCRIPT_DIR / "config.json"
        if not cfg.exists():
            messagebox.showwarning("Not found",
                                   "config.json not found.\n"
                                   "Copy config.example.json to config.json first.")
            return
        os.startfile(cfg)        # opens in default editor (Notepad etc.)

    # ------------------------------------------------------------------
    # System tray
    # ------------------------------------------------------------------
    def _make_tray_image(self):
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d   = ImageDraw.Draw(img)
        color = (0, 201, 106) if self.running else (74, 74, 106)
        d.ellipse([4, 4, 60, 60], fill=color)
        return img

    def _minimize_to_tray(self):
        self.root.withdraw()
        img  = self._make_tray_image()
        menu = pystray.Menu(
            pystray.MenuItem("Show Window",    self._show_from_tray, default=True),
            pystray.MenuItem("Start / Stop",   lambda: self.root.after(0, self.toggle)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Send Summary Now", lambda: self.root.after(0, self._send_now)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit",           lambda: self.root.after(0, self._quit)),
        )
        self._tray_icon = pystray.Icon(
            "meeting_monitor", img, "Meeting Monitor", menu)
        threading.Thread(target=self._tray_icon.run, daemon=True).start()

    def _show_from_tray(self, *_):
        if self._tray_icon:
            self._tray_icon.stop()
            self._tray_icon = None
        self.root.after(0, self.root.deiconify)

    # ------------------------------------------------------------------
    # Close / quit
    # ------------------------------------------------------------------
    def _on_close(self):
        if self.running:
            if TRAY_AVAILABLE:
                answer = messagebox.askyesnocancel(
                    "Still running",
                    "The monitor is active.\n\n"
                    "• Yes   → Minimise to system tray (keeps recording)\n"
                    "• No    → Stop and quit\n"
                    "• Cancel → Go back",
                )
                if answer is True:
                    self._minimize_to_tray()
                elif answer is False:
                    self._quit()
                # None → cancel, do nothing
            else:
                if messagebox.askyesno("Still running",
                                       "The monitor is active. Stop it and quit?"):
                    self._quit()
        else:
            self._quit()

    def _quit(self):
        if self._tray_icon:
            self._tray_icon.stop()
        self._stop()
        self.root.destroy()

    # ------------------------------------------------------------------
    def run(self):
        self.root.mainloop()


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = MeetingMonitorApp()
    app.run()
