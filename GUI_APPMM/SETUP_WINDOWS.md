# 🪟 Windows Setup & Deployment Guide

> **Meeting Monitor** — Record Teams calls, transcribe locally with Whisper, summarize with Claude AI, and receive a daily email summary.

---

## 📋 Table of Contents

- [Prerequisites](#prerequisites)
- [Part 1 — Project Setup](#part-1--project-setup)
- [Part 2 — Claude CLI Installation](#part-2--claude-cli-installation)
- [Running the App](#running-the-app)
- [Optional — Run on Startup](#optional--run-on-startup)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

| Requirement | Minimum Version | Download |
|---|---|---|
| Python | 3.10+ | https://python.org/downloads |
| Node.js *(only if using npm install method for Claude CLI)* | 18+ | https://nodejs.org |
| Git for Windows *(required for Claude CLI native install)* | Any | https://git-scm.com/download/win |
| Anthropic API Key | — | https://console.anthropic.com |
| Gmail App Password | — | https://myaccount.google.com/apppasswords |

---

## Part 1 — Project Setup

### Step 1 — Install Python

1. Download the installer from https://python.org/downloads
2. Run it and **tick "Add Python to PATH"** before clicking Install
3. Open a new terminal and verify:

```powershell
python --version
```

Expected output: `Python 3.10.x` or higher

---

### Step 2 — Create project folder and add files

```powershell
mkdir C:\meeting-monitor
cd C:\meeting-monitor
```

Copy these files into `C:\meeting-monitor\`:

```
meeting-monitor/
├── main.py
├── config.json
├── config.example.json
├── requirements.txt
└── README.md
```

---

### Step 3 — Create a virtual environment

```powershell
python -m venv venv
venv\Scripts\activate
```

> Your terminal prompt will show `(venv)` when active. Always activate this before running the app.

---

### Step 4 — Install Python dependencies

```powershell
pip install -r requirements.txt
```

**If `sounddevice` fails on Windows**, also run:

```powershell
pip install pipwin
pipwin install pyaudio
```

---

### Step 5 — Configure `config.json`

Open `config.json` in Notepad or VS Code and fill in the required fields:

```json
{
  "anthropic_api_key": "sk-ant-xxxxxxxxxxxxxxxx",

  "recordings_dir": "recordings",
  "audio_device_index": 4,

  "whisper_model": "small",

  "summary_time": "18:00",

  "check_interval_seconds": 5,
  "audio_threshold": 0.001,

  "email": {
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587,
    "username": "your-email@gmail.com",
    "password": "your-16-char-app-password",
    "from_email": "your-email@gmail.com",
    "to_email": "your-email@gmail.com"
  }
}
```

#### Getting your Anthropic API Key

1. Go to https://console.anthropic.com
2. Navigate to **API Keys**
3. Click **Create Key** and copy the key starting with `sk-ant-`

#### Getting your Gmail App Password

1. Enable **2-Factor Authentication** on your Google account
2. Go to https://myaccount.google.com/apppasswords
3. Create an App Password for **"Mail"**
4. Paste the 16-character code into `"password"`

> **Outlook users:** use `smtp.office365.com`, port `587`, and your regular password.

---

### Step 6 — Find your microphone device index

```powershell
python -c "import sounddevice as sd; print(sd.query_devices())"
```

This prints a list like:

```
0  Microsoft Sound Mapper - Input
1  Microphone (Realtek Audio)
4  Headset Microphone (USB)
...
```

Note the index of your preferred microphone and set it in `config.json`:

```json
"audio_device_index": 4
```

---

## Part 2 — Claude CLI Installation

Claude Code is Anthropic's official command-line AI tool. There are two install methods — the **native installer is recommended**.

---

### Method A — Native Installer (Recommended ✅)

No Node.js required. Run this in **PowerShell**:

```powershell
irm https://claude.ai/install.ps1 | iex
```

> After installation finishes, **close your terminal and open a new one** — this is required for PATH changes to apply.

**Verify installation:**

```powershell
claude --version
```

**Authenticate:**

```powershell
claude
```

A browser window will open automatically. Log in with your Anthropic account to complete OAuth — no API key needed.

**Run a health check:**

```powershell
claude doctor
```

---

### Method B — npm Install (Alternative)

Use this if you already have Node.js 18+ installed.

```powershell
npm install -g @anthropic-ai/claude-code
```

**Verify:**

```powershell
claude --version
```

**Authenticate:**

```powershell
claude
```

> ⚠️ Do **not** use `sudo npm install -g` — it creates file ownership problems.

**If `claude` is not recognized after install**, add npm's global bin to your PATH:

```powershell
[Environment]::SetEnvironmentVariable(
  "PATH",
  "$env:PATH;$env:APPDATA\npm",
  [EnvironmentVariableTarget]::User
)
```

Then open a new terminal and retry.

---

### Using Claude CLI inside the project

```powershell
cd C:\meeting-monitor
venv\Scripts\activate
claude
```

You can then ask Claude Code things like:
- `"Review main.py and check for any bugs"`
- `"Explain how the Summarizer class works"`
- `"Help me tune the audio_threshold in config.json"`

---

## Running the App

```powershell
cd C:\meeting-monitor
venv\Scripts\activate
python main.py
```

Expected output:

```
2025-01-15 09:00:01  INFO  Loading Whisper model 'small'...
2025-01-15 09:00:04  INFO  Whisper model ready.
2025-01-15 09:00:04  INFO  Daily summary scheduled at 18:00
2025-01-15 09:00:04  INFO  👀 Monitoring for Microsoft Teams calls…
2025-01-15 09:00:04  INFO  Meeting Monitor running. Press Ctrl+C to quit.
```

When a Teams call is detected:

```
2025-01-15 10:30:12  INFO  ▶ Recording started → teams_20250115_103012.wav
2025-01-15 11:15:44  INFO  ■ Recording saved: teams_20250115_103012.wav (2732s)
```

Stop the app anytime with `Ctrl+C`.

---

## Optional — Run on Startup (Task Scheduler)

To have Meeting Monitor launch automatically when you log into Windows:

1. Open **Task Scheduler** → click **"Create Basic Task"**
2. **Name:** `Meeting Monitor`
3. **Trigger:** `When I log on`
4. **Action:** `Start a Program`
   - **Program/script:** full path to your venv Python, e.g.
     ```
     C:\meeting-monitor\venv\Scripts\pythonw.exe
     ```
   - **Arguments:**
     ```
     main.py
     ```
   - **Start in:**
     ```
     C:\meeting-monitor
     ```
5. Click **Finish**

> Use `pythonw.exe` (not `python.exe`) so no console window appears in the background.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| **False positives** — app records when not in a call | Increase `audio_threshold` to `0.015` or `0.02` in `config.json` |
| **Missed calls** — stops recording too early | Decrease `audio_threshold` to `0.005` |
| **Email not sending** | Verify App Password is correct and 2FA is enabled on Gmail. Check `meeting_monitor.log` for the exact error |
| **`claude` not recognized in terminal** | Close and reopen terminal after install. If still failing, check PATH as described in Method B above |
| **Whisper model slow on first run** | One-time download only. Switch to `"whisper_model": "tiny"` for faster startup |
| **Teams not detected** | Open Task Manager → Details tab → find the exact `.exe` name and update `TEAMS_PROCESS_NAMES` in `main.py` |
| **`sounddevice` install error** | Run `pip install pipwin` then `pipwin install pyaudio` |
| **`venv\Scripts\activate` not working** | Run `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` in PowerShell first |

---

## File Structure

```
meeting-monitor/
├── main.py                   # Main application
├── config.json               # Your configuration (keep private)
├── config.example.json       # Template for reference
├── requirements.txt          # Python dependencies
├── SETUP_WINDOWS.md          # This guide
├── README.md                 # Project overview
├── meeting_monitor.log       # Runtime log (auto-created)
└── recordings/               # WAV recordings (auto-created)
    ├── teams_20250115_103012.wav
    └── ...
```

---

## Configuration Reference

| Key | Default | Description |
|---|---|---|
| `anthropic_api_key` | — | Your key from https://console.anthropic.com |
| `whisper_model` | `"small"` | `tiny` fastest, `medium`/`large` most accurate |
| `summary_time` | `"18:00"` | Daily email send time (24h format) |
| `check_interval_seconds` | `5` | How often the app polls for an active call |
| `audio_threshold` | `0.001` | Mic RMS level above which audio is "active" |
| `audio_device_index` | `4` | Index from `sd.query_devices()` output |
| `recordings_dir` | `"recordings"` | Folder where `.wav` files are saved |
