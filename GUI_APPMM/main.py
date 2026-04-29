#!/usr/bin/env python3
"""
Meeting Monitor
===============
Detects active Microsoft Teams calls, records audio via system microphone,
transcribes with Whisper (local), summarizes with Claude API, and emails
you a daily bullet-point summary.

Supported OS: Windows & macOS
"""

import os
import sys
import json
import time
import wave
import smtplib
import logging
import threading
import datetime
import collections
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import psutil
import numpy as np
import sounddevice as sd
import anthropic
import schedule
from faster_whisper import WhisperModel

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CONFIG_FILE = Path(__file__).parent / "config.json"

def load_config() -> dict:
    if not CONFIG_FILE.exists():
        print(f"ERROR: config.json not found at {CONFIG_FILE}")
        print("Copy config.example.json to config.json and fill in your details.")
        sys.exit(1)
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Teams Process Detection
# ---------------------------------------------------------------------------

# Process names for each platform
TEAMS_PROCESS_NAMES = {
    "win32":  ["ms-teams.exe", "Teams.exe", "ms-teamsupdate.exe"],
    "darwin": ["Microsoft Teams", "Microsoft Teams (work or school)", "MSTeams"],
    "linux":  ["teams", "teams-insiders"],
}

def get_running_process_names() -> set:
    names = set()
    for p in psutil.process_iter(["name"]):
        try:
            names.add(p.info["name"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return names

def is_teams_running() -> bool:
    platform_key = sys.platform
    targets = TEAMS_PROCESS_NAMES.get(platform_key, [])
    running = get_running_process_names()
    return any(t in running for t in targets)


# ---------------------------------------------------------------------------
# Audio Activity Detection
# ---------------------------------------------------------------------------

class AudioActivityDetector:
    """
    Samples the default microphone for a short burst and returns the RMS level.
    Uses a rolling history to smooth out spikes / silence gaps.
    """

    def __init__(self, samplerate: int = 16000, window_seconds: float = 1.0, threshold: float = 0.008, device_index: int | None = None):
        self.samplerate = samplerate
        self.window_samples = int(samplerate * window_seconds)
        self.threshold = threshold
        self.device_index = device_index
        # Rolling history of RMS values (last N samples)
        self._rms_history: collections.deque = collections.deque(maxlen=6)

    def sample_rms(self) -> float:
        """Capture a short audio burst and return RMS."""
        try:
            data = sd.rec(
                self.window_samples,
                samplerate=self.samplerate,
                channels=1,
                dtype="float32",
                blocking=True,
                device=self.device_index,
            )
            rms = float(np.sqrt(np.mean(data ** 2)))
            self._rms_history.append(rms)
            return rms
        except Exception as exc:
            logging.debug(f"Audio sample error: {exc}")
            return 0.0

    def is_active(self) -> bool:
        """True if the rolling average RMS exceeds the threshold."""
        rms = self.sample_rms()
        if len(self._rms_history) < 2:
            return rms > self.threshold
        avg = sum(self._rms_history) / len(self._rms_history)
        return avg > self.threshold


# ---------------------------------------------------------------------------
# Audio Recorder
# ---------------------------------------------------------------------------

class AudioRecorder:
    """
    Records from the default microphone to a WAV file.
    On Windows, sounddevice uses the Windows Core Audio / WASAPI stack.
    On macOS, it uses Core Audio.
    No third-party virtual drivers required.
    """

    SAMPLERATE = 16000  # 16 kHz mono — optimal for Whisper
    CHANNELS   = 1

    def __init__(self, output_dir: Path, device_index: int | None = None):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.device_index = device_index
        self._recording  = False
        self._frames: list = []
        self._stream     = None
        self._current_path: Path | None = None
        self._start_time: datetime.datetime | None = None

    # ------------------------------------------------------------------
    def start(self, label: str = "") -> None:
        if self._recording:
            return
        ts    = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        name  = f"teams_{ts}" if not label else f"teams_{ts}_{label}"
        self._current_path = self.output_dir / f"{name}.wav"
        self._frames  = []
        self._recording = True
        self._start_time = datetime.datetime.now()

        def _callback(indata, frames, t, status):
            if status:
                logging.debug(f"Audio callback status: {status}")
            if self._recording:
                self._frames.append(indata.copy())

        self._stream = sd.InputStream(
            samplerate=self.SAMPLERATE,
            channels=self.CHANNELS,
            dtype="float32",
            callback=_callback,
            device=self.device_index,
        )
        self._stream.start()
        logging.info(f"▶ Recording started → {self._current_path.name}")

    # ------------------------------------------------------------------
    def stop(self) -> tuple[Path | None, datetime.datetime | None]:
        if not self._recording:
            return None, None
        self._recording = False
        start_time = self._start_time

        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        if not self._frames:
            logging.warning("No audio frames captured.")
            return None, None

        audio = np.concatenate(self._frames, axis=0)
        audio_i16 = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)

        with wave.open(str(self._current_path), "wb") as wf:
            wf.setnchannels(self.CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(self.SAMPLERATE)
            wf.writeframes(audio_i16.tobytes())

        duration_s = len(audio_i16) / self.SAMPLERATE
        logging.info(f"■ Recording saved: {self._current_path.name} ({duration_s:.0f}s)")
        return self._current_path, start_time

    @property
    def is_recording(self) -> bool:
        return self._recording


# ---------------------------------------------------------------------------
# Transcriber (local Whisper via faster-whisper)
# ---------------------------------------------------------------------------

class Transcriber:
    def __init__(self, model_size: str = "base"):
        logging.info(f"Loading Whisper model '{model_size}' (first run downloads ~150 MB)…")
        self.model = WhisperModel(model_size, device="cpu", compute_type="int8")
        logging.info("Whisper model ready.")

    def transcribe(self, audio_path: Path) -> str:
        logging.info(f"Transcribing {audio_path.name}…")
        # Providing an initial prompt helps Whisper handle mixed languages (Hinglish)
        # and technical terminology more accurately.
        prompt = "This is a meeting transcript in Hinglish, mixing Hindi and English words like: meeting, schedule, discuss, call, update, okay, fine, नमस्ते, ठीक है, शुक्रिया।"
        
        segments, info = self.model.transcribe(
            str(audio_path), 
            beam_size=5, 
            initial_prompt=prompt
        )
        text = " ".join(seg.text.strip() for seg in segments)
        logging.info(f"Transcription complete ({info.duration:.0f}s audio, lang={info.language})")
        return text or "[No speech detected]"


# ---------------------------------------------------------------------------
# Summariser (Anthropic Claude API)
# ---------------------------------------------------------------------------

class Summarizer:
    MODEL = "claude-sonnet-4-5"

    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)

    def summarize(self, meetings: list[dict]) -> str:
        """
        meetings = [{"label": str, "start_time": str, "duration": str, "transcript": str}, …]
        """
        today = datetime.date.today().strftime("%A, %B %d %Y")
        total = len(meetings)

        blocks = ""
        for i, m in enumerate(meetings, 1):
            blocks += (
                f"\n--- Meeting {i} of {total} ---\n"
                f"Label:    {m['label']}\n"
                f"Started:  {m['start_time']}\n"
                f"Duration: {m['duration']}\n"
                f"Transcript:\n{m['transcript']}\n"
            )

        prompt = f"""You are an executive assistant preparing a daily recap email.
Today is {today}. Below are transcripts from {total} recorded Microsoft Teams meeting(s).

{blocks}

Please write a clear, well-structured end-of-day summary with these sections:

## 👥 Participants
- List all individuals who spoke or were mentioned as present.

## 📋 Overview
A 2-3 sentence high-level summary of the day's meetings.

## ✅ Key Decisions
- Bullet each major decision made across all meetings.

## 📌 Action Items
- List every task mentioned. 
- **Owner:** Identify the specific name of the person responsible. If a name isn't used, look for "I" (the speaker) or "You" and try to infer from the context.
- **Task:** Detailed description of the work.
- **Deadline:** Mention any dates or timeframes discussed.
- If the owner cannot be determined, label as "Owner: Unassigned".

## 💬 Key Discussion Points
- Most important topics discussed across all meetings.

## 🔁 Follow-ups Required
- Things that need follow-up, clarification, or are still unresolved.

Be concise and professional. Use plain text bullets (not markdown formatting in the email body)."""

        message = self.client.messages.create(
            model=self.MODEL,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text


# ---------------------------------------------------------------------------
# Email Sender
# ---------------------------------------------------------------------------

class EmailSender:
    def __init__(self, cfg: dict):
        self.host      = cfg["smtp_host"]
        self.port      = int(cfg["smtp_port"])
        self.username  = cfg["username"]
        self.password  = cfg["password"]
        self.from_addr = cfg["from_email"]
        self.to_addr   = cfg["to_email"]

    def send(self, subject: str, body: str) -> None:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = self.from_addr
        msg["To"]      = self.to_addr
        msg.attach(MIMEText(body, "plain", "utf-8"))

        with smtplib.SMTP(self.host, self.port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.login(self.username, self.password)
            server.sendmail(self.from_addr, [self.to_addr], msg.as_string())

        logging.info(f"📧 Summary email sent to {self.to_addr}")


# ---------------------------------------------------------------------------
# Meeting Monitor — main orchestrator
# ---------------------------------------------------------------------------

class MeetingMonitor:

    # How many consecutive silent checks before we consider a call over
    SILENCE_CHECKS_TO_STOP = 4   # × check_interval seconds

    def __init__(self):
        self.cfg        = load_config()
        rec_dir         = Path(self.cfg.get("recordings_dir", "recordings"))
        threshold       = float(self.cfg.get("audio_threshold", 0.008))
        check_interval  = int(self.cfg.get("check_interval_seconds", 5))
        device_index    = self.cfg.get("audio_device_index")

        self.detector   = AudioActivityDetector(threshold=threshold, device_index=device_index)
        self.recorder   = AudioRecorder(rec_dir, device_index=device_index)
        self.transcriber= Transcriber(self.cfg.get("whisper_model", "base"))
        self.summarizer = Summarizer(self.cfg["anthropic_api_key"])
        self.emailer    = EmailSender(self.cfg["email"])

        self.check_interval = check_interval
        self._in_call       = False
        self._silence_count = 0
        self._call_start: datetime.datetime | None = None
        self._today_meetings: list[dict] = []

    # ------------------------------------------------------------------
    # Monitoring loop (runs in background thread)
    # ------------------------------------------------------------------

    def _monitor_loop(self):
        logging.info("👀 Monitoring for Microsoft Teams calls…")
        while True:
            try:
                self._tick()
            except Exception as exc:
                logging.error(f"Monitor tick error: {exc}")
            time.sleep(self.check_interval)

    def _tick(self):
        teams_up   = is_teams_running()
        audio_live = self.detector.is_active() if teams_up else False

        if teams_up and audio_live:
            self._silence_count = 0
            if not self._in_call:
                self._start_recording()

        elif self._in_call:
            if not teams_up:
                # Teams closed — stop immediately
                logging.info("Teams closed — stopping recording.")
                self._stop_recording()
            else:
                # Silence gap — wait before stopping
                self._silence_count += 1
                if self._silence_count >= self.SILENCE_CHECKS_TO_STOP:
                    logging.info("Sustained silence detected — call likely ended.")
                    self._stop_recording()

    def _start_recording(self):
        self._in_call    = True
        self._silence_count = 0
        self._call_start = datetime.datetime.now()
        self.recorder.start()

    def _stop_recording(self):
        self._in_call = False
        path, start = self.recorder.stop()
        if path and start:
            end = datetime.datetime.now()
            duration_min = int((end - start).total_seconds() / 60)
            self._today_meetings.append({
                "label":      path.stem,
                "start_time": start.strftime("%H:%M"),
                "duration":   f"{duration_min} min",
                "audio_path": path,
                "transcript": None,   # filled later
            })

    # ------------------------------------------------------------------
    # Daily summary job
    # ------------------------------------------------------------------

    def _daily_summary(self):
        logging.info("⏰ Daily summary triggered…")

        # Stop any in-progress recording first
        if self._in_call:
            self._stop_recording()

        if not self._today_meetings:
            logging.info("No meetings recorded today — nothing to summarize.")
            return

        # Transcribe each recording
        for m in self._today_meetings:
            if m["transcript"] is None:
                try:
                    m["transcript"] = self.transcriber.transcribe(m["audio_path"])
                except Exception as exc:
                    logging.error(f"Transcription failed for {m['audio_path']}: {exc}")
                    m["transcript"] = "[Transcription failed]"

        # Summarize
        try:
            summary = self.summarizer.summarize(self._today_meetings)
        except Exception as exc:
            logging.error(f"Summarization failed: {exc}")
            return

        # Email
        today_str = datetime.date.today().strftime("%B %d, %Y")
        subject   = f"📋 Daily Meeting Summary — {today_str} ({len(self._today_meetings)} meeting(s))"
        try:
            self.emailer.send(subject, summary)
        except Exception as exc:
            logging.error(f"Email failed: {exc}")
            # Save to file as fallback
            fallback = Path("summary_fallback.txt")
            fallback.write_text(summary, encoding="utf-8")
            logging.info(f"Summary saved to {fallback} as fallback.")

        # Reset for next day
        self._today_meetings.clear()

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def run(self):
        log_path = Path(__file__).parent / "meeting_monitor.log"
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s  %(levelname)-8s  %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            handlers=[
                logging.FileHandler(log_path, encoding="utf-8"),
                logging.StreamHandler(sys.stdout),
            ],
            force=True
        )
        # Ensure log file is created and written to immediately
        logging.info("--- Meeting Monitor Starting ---")

        summary_time = self.cfg.get("summary_time", "18:00")
        schedule.every().day.at(summary_time).do(self._daily_summary)
        logging.info(f"Daily summary scheduled at {summary_time}")

        # Background monitoring thread
        t = threading.Thread(target=self._monitor_loop, daemon=True)
        t.start()

        logging.info("Meeting Monitor running. Press Ctrl+C to quit.")
        trigger_file = Path(__file__).parent / ".send_summary_now"
        try:
            while True:
                schedule.run_pending()
                # Check for manual summary trigger from GUI
                if trigger_file.exists():
                    try:
                        trigger_file.unlink()
                        logging.info("Manual summary trigger received from GUI.")
                        threading.Thread(target=self._daily_summary, daemon=True).start()
                    except Exception as exc:
                        logging.error(f"Trigger file error: {exc}")
                time.sleep(1)
        except KeyboardInterrupt:
            logging.info("Shutting down…")
            if self._in_call:
                self.recorder.stop()
            sys.exit(0)


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = MeetingMonitor()
    app.run()
