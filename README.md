# Meeting Monitor 🎙️

Automatically records Microsoft Teams calls, transcribes them locally with Whisper,
and emails you a clean bullet-point summary at the end of every day — powered by Gemini AI.

---

## How It Works

```
Teams call starts
       ↓
Microphone audio level rises → app detects call
       ↓
Records audio via OS built-in audio stack (WASAPI on Windows / Core Audio on Mac)
       ↓
Call ends → audio saved as .wav file
       ↓
At your scheduled time (default 6:00 PM):
  → All recordings transcribed locally with Whisper (no data leaves your machine)
  → Transcripts sent to Gemini API for summarization
  → Summary emailed to you
```

No third-party bots, no screen sharing, no cloud uploads of your audio.

---

## Prerequisites

- Python 3.10 or higher
- A microphone (built-in or external)
- An [Anthropic API key](https://console.anthropic.com/)
- A Gmail / Outlook / Yahoo email account

---

## Setup

### 1. Install Python

- **Windows**: Download from https://python.org — tick "Add Python to PATH"
- **Mac**: `brew install python` (or download from python.org)

---

### 2. Install dependencies

Open Terminal (Mac) or Command Prompt (Windows) in the project folder:

```bash
pip install -r requirements.txt
```

**Windows note**: If sounddevice fails, also run:
```bash
pip install pipwin
pipwin install pyaudio
```

**Mac note**: If sounddevice fails, run:
```bash
brew install portaudio
pip install sounddevice
```

---

### 3. Configure the app

Copy the example config and edit it:

```bash
# Mac / Linux
cp config.example.json config.json

# Windows
copy config.example.json config.json
```

Open `config.json` and fill in:

| Field | What to put |
|-------|-------------|
| `anthropic_api_key` | Your key from https://console.anthropic.com/ |
| `summary_time` | Time to send daily email, e.g. `"18:00"` |
| `email.username` | Your email address |
| `email.password` | App password (see below) |
| `email.to_email` | Where to send the summary (can be same address) |

#### Gmail App Password (recommended)
1. Enable 2-Factor Authentication on your Google account
2. Go to https://myaccount.google.com/apppasswords
3. Create an app password for "Mail"
4. Paste the 16-character code into `email.password`

#### Outlook / Office 365
Use `smtp.office365.com` port `587` and your regular password (or App Password if MFA is on).

---

### 4. Run the app

```bash
python main.py
```

You'll see output like:
```
2025-01-15 09:00:01  INFO     Loading Whisper model 'base'...
2025-01-15 09:00:04  INFO     Whisper model ready.
2025-01-15 09:00:04  INFO     Daily summary scheduled at 18:00
2025-01-15 09:00:04  INFO     👀 Monitoring for Microsoft Teams calls…
2025-01-15 09:00:04  INFO     Meeting Monitor running. Press Ctrl+C to quit.
```

When a Teams call is detected:
```
2025-01-15 10:30:12  INFO     ▶ Recording started → teams_20250115_103012.wav
2025-01-15 11:15:44  INFO     ■ Recording saved: teams_20250115_103012.wav (2732s)
```

---

## Run on Startup (optional but recommended)

### Windows — Task Scheduler

1. Open Task Scheduler → "Create Basic Task"
2. Trigger: "When I log on"
3. Action: Start a Program
   - Program: `pythonw.exe` (use full path, e.g. `C:\Python312\pythonw.exe`)
   - Arguments: `main.py`
   - Start in: full path to the project folder
4. Finish

### Mac — Launch Agent

Create `~/Library/LaunchAgents/com.meetingmonitor.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.meetingmonitor</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/python3</string>
        <string>/full/path/to/meeting_monitor/main.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>/full/path/to/meeting_monitor</string>
    <key>StandardOutPath</key>
    <string>/tmp/meeting_monitor.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/meeting_monitor_err.log</string>
</dict>
</plist>
```

Then run:
```bash
launchctl load ~/Library/LaunchAgents/com.meetingmonitor.plist
```

---

## Configuration Reference

| Key | Default | Description |
|-----|---------|-------------|
| `whisper_model` | `"base"` | Whisper model size. `tiny` is fastest, `medium`/`large` are more accurate |
| `summary_time` | `"18:00"` | Daily summary send time (24h format) |
| `check_interval_seconds` | `5` | How often to sample mic audio |
| `audio_threshold` | `0.008` | Mic RMS threshold to consider a call active. Raise this if noisy room |
| `recordings_dir` | `"recordings"` | Folder where .wav files are saved |

---

## Troubleshooting

**App detects calls when I'm not on one (false positives)**
→ Increase `audio_threshold` to `0.015` or `0.02` in config.json

**App misses calls / stops recording early**
→ Decrease `audio_threshold` to `0.005`

**Email not sending**
→ Check your App Password is correct. For Gmail, make sure 2FA is enabled.
→ Check `meeting_monitor.log` for the exact error.

**Whisper model download slow on first run**
→ This is a one-time download. `base` is ~145 MB. Run with `"whisper_model": "tiny"` to start faster.

**Teams not detected on Windows**
→ Newer Teams (2.0) uses `ms-teams.exe`. Check Task Manager → Details tab for the exact process name and update `TEAMS_PROCESS_NAMES` in `main.py` if needed.

---

## Privacy

- All audio is stored locally in the `recordings/` folder
- Transcription runs entirely on your machine (Whisper runs offline)
- Only the text transcript is sent to the Anthropic API for summarization
- You can delete recordings from `recordings/` at any time

---

## File Structure

```
meeting_monitor/
├── main.py                  # Main application
├── config.json              # Your configuration (gitignored)
├── config.example.json      # Template
├── requirements.txt         # Python dependencies
├── README.md                # This file
├── meeting_monitor.log      # Runtime log (auto-created)
└── recordings/              # WAV recordings (auto-created)
    ├── teams_20250115_103012.wav
    └── ...
```
