# Shams: The Digital Observer

An embodied AI agent on Raspberry Pi that listens, sees, detects motion, and autonomously responds through voice, OLED expression, camera, Telegram alerts, Gmail checks, and UiPath-triggered enterprise workflows.

## Overview

Shams is a local AI companion and autonomous observer designed to move beyond a chatbot into a real-world decision-making agent. Running on a Raspberry Pi, it combines multiple sensors and communication channels to create a truly interactive and responsive AI presence.

## Features

### Sensing & Input
- 🎤 Voice interaction via Fusion HAT microphone
- 📷 Camera capture and image processing
- 📡 PIR motion detection
- 📏 Ultrasonic distance sensing
- 📧 Gmail integration (unread email summaries)
- 🔄 UiPath enterprise workflow events

### Processing & Intelligence
- 🧠 Ollama-powered local reasoning (no cloud dependency)
- 💾 SQLite-based memory and task management
- 🎯 Context-aware response generation
- 🔒 Local privacy-first processing

### Output & Actions
- 🔊 TTS voice responses
- 🖼️ OLED animated face display
- 📱 Telegram notifications and alerts
- 📸 Automated photo capture and sending
- ⚙️ UiPath workflow triggers

## Hardware Requirements

- Raspberry Pi 4 or 5 (4GB+ RAM recommended)
- Fusion HAT with microphone and speaker
- OLED display (128x64 or compatible)
- PIR motion sensor
- Ultrasonic distance sensor (HC-SR04)
- Camera module

## Software Requirements

- Python 3.9+
- Ollama (for local LLM inference)
- Flask (for UiPath bridge)
- gpiozero (for sensor handling)
- Google API libraries (for Gmail)

## Installation

```bash
# Clone the repository
git clone https://github.com/Rahaaaf/shams-digital-observer.git
cd shams-digital-observer

# Install Python dependencies
python3 -m pip install -r requirements.txt --break-system-packages

# Install Ollama (on Raspberry Pi)
curl -fsSL https://ollama.ai/install.sh | sh

# Pull a model (e.g., Qwen 2.5 3B)
ollama pull qwen2.5:3b
```

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# UiPath Security
export UIPATH_SECRET="your-secret-key-here"

# Gmail Integration
export GOOGLE_APPLICATION_CREDENTIALS="path/to/credentials.json"

# Telegram (Optional)
export TELEGRAM_BOT_TOKEN="your-bot-token"
export TELEGRAM_CHAT_ID="your-chat-id"
```

### GPIO Pin Configuration

Edit the pin assignments in `codex.py`:

```python
TRIG_PIN = 23   # Ultrasonic trigger
ECHO_PIN = 24   # Ultrasonic echo
PIR_PIN = 22    # Motion sensor
```

## Running Shams

```bash
python3 codex.py
```

The system will:
1. Initialize all sensors and connections
2. Load the OLED face
3. Start the UiPath bridge on `http://localhost:5055`
4. Wait for voice input or external events

## Architecture

```
┌─────────────────────────────────────────┐
│     Physical & Digital World Inputs     │
├─────────────────────────────────────────┤
│ Voice | Motion | Distance | Camera      │
│ Gmail | UiPath Events | Notifications  │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼─────────────────────���────┐
│      Raspberry Pi: Shams Core           │
├──────────────────────────────────────────┤
│ - HAT STT (Vosk speech recognition)    │
│ - Memory (SQLite tasks & chat history) │
│ - Ollama Brain (local LLM reasoning)   │
│ - Sensor handlers                       │
│ - Flask UiPath bridge                   │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│      Autonomous Actions & Responses     │
├──────────────────────────────────────────┤
│ Voice (TTS) | OLED | Telegram          │
│ Camera Capture | Workflow Triggers     │
└──────────────────────────────────────────┘
```

## UiPath Integration

### Setup in UiPath

Use the **HTTP Request** activity with these settings:

**Method:** POST  
**URL:** `http://<raspberry-pi-ip>:5055/event`

**Headers:**
```
Content-Type: application/json
X-Shams-Secret: your-secret-key
```

**Body (JSON):**
```json
{
  "source": "uipath",
  "event": "too_many_tabs",
  "level": "warning",
  "message": "You opened too many tabs. Are you searching for knowledge, or escaping silence?"
}
```

### Example Events

#### Long Focus Session
```json
{
  "event": "long_focus",
  "level": "soft_warning",
  "message": "You have been focused for three hours. Even machines need cooling."
}
```

#### Idle Computer
```json
{
  "event": "idle",
  "level": "info",
  "message": "The room is quiet. Maybe this is a good moment to breathe."
}
```

#### Notification Overload
```json
{
  "event": "notification_overload",
  "level": "warning",
  "message": "Your screen is asking for attention again. But not everything deserves your mind."
}
```

## Testing

### Test UiPath Bridge

```bash
curl -X POST http://localhost:5055/event \
  -H "Content-Type: application/json" \
  -H "X-Shams-Secret: your-secret-key" \
  -d '{
    "source":"test",
    "event":"too_many_tabs",
    "level":"warning",
    "message":"You opened too many tabs."
  }'
```

### Voice Commands

Once running, try these voice commands:

- **"Hello Shams"** - Start interaction
- **"Take a photo of me"** - Capture image
- **"How far am I?"** - Check distance
- **"Check my email"** - Gmail summary
- **"Tell me a story"** - Special narrative
- **"Remind me to..."** - Save task
- **"What are my tasks?"** - List tasks
- **"Done"** - Complete a task
- **"Exit"** - Shutdown system

## File Structure

```
shams-digital-observer/
├── codex.py                 # Main Shams core
├── uipath_bridge.py         # Flask-based UiPath event handler
├── hat_stt.py               # Fusion HAT speech-to-text
├── oled_shams.py            # OLED display controller
├── telegram_notify.py        # Telegram notifications
├── brain.py                 # Ollama integration
├── requirements.txt         # Python dependencies
├── README.md                # This file
├── LICENSE                  # Open source license
└── photos/                  # Auto-generated photo directory
```

## API Endpoints

### GET `/`
Returns bridge status and system info.

```bash
curl http://localhost:5055/
```

Response:
```json
{
  "ok": true,
  "name": "Shams UiPath Bridge",
  "time": "2026-05-18T14:30:45"
}
```

### POST `/event`
Receive and process UiPath events.

**Headers:**
- `X-Shams-Secret` (if `UIPATH_SECRET` is set)
- `Content-Type: application/json`

**Body Fields:**
- `source` (string): Event source (e.g., "uipath")
- `event` (string): Event type/name
- `message` (string): Optional custom message
- `level` (string): Severity ("info", "warning", "soft_warning")

**Response:**
```json
{
  "ok": true,
  "received": {
    "source": "uipath",
    "event": "too_many_tabs",
    "message": "...",
    "level": "warning",
    "time": "2026-05-18T14:30:45"
  }
}
```

## Extending Shams

### Add a New Sensor

1. Create a handler in `BodySensors` class
2. Add initialization in `Shams.__init__()`
3. Create logic in `think()` method

### Add a New Command

1. Add pattern matching in `think()` method
2. Implement handler function
3. Return response text

### Add a New Output Channel

1. Create a new module (e.g., `discord_notify.py`)
2. Implement event handler
3. Initialize in `Shams.__init__()`

## Privacy & Security

- **Local Processing:** All LLM inference runs locally on the Pi
- **No Cloud Storage:** Memories stored in local SQLite database
- **Secret Authorization:** UiPath events require `X-Shams-Secret` header
- **GPIO-Only Control:** Physical sensors prevent unauthorized remote access

## Future Roadmap

- [ ] Multi-language support
- [ ] Advanced gesture recognition
- [ ] Long-term behavioral memory analysis
- [ ] Custom skill plugins
- [ ] Web dashboard for configuration
- [ ] Integration with more automation platforms (Zapier, IFTTT)
- [ ] Distributed multi-Pi systems

## Troubleshooting

### Flask Not Installed
```bash
python3 -m pip install flask --break-system-packages
```

### Ollama Not Responding
```bash
ollama serve
# In another terminal:
ollama pull qwen2.5:3b
```

### GPIO Permission Errors
```bash
sudo usermod -a -G gpio $USER
# Then log out and log back in
```

### Audio Not Working
```bash
arecord -l  # Check playback devices
alsamixer   # Adjust volume levels
```

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

MIT License - See LICENSE file for details

## Disclaimer

This project is provided as-is. Ensure all sensors are properly installed and configured before running. Always test hardware safely. UiPath integration requires proper authentication and network configuration.

## Citation

If you use Shams in your research or project, please cite:

```bibtex
@software{shams2026,
  author = {Rahaaaf},
  title = {Shams: The Digital Observer - An Embodied AI Agent},
  year = {2026},
  url = {https://github.com/Rahaaaf/shams-digital-observer}
}
```

---

**Shams: I see. I learn. I understand.**
