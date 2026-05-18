#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import sqlite3
import datetime
import subprocess
import threading
import time
from pathlib import Path

from hat_stt import HatSTT
from telegram_notify import TelegramNotifier
from oled_shams import ShamsOLED
from uipath_bridge import UiPathBridge

NAME = "Shams"
USER_NAME = "User"

BASE_DIR = Path(__file__).resolve().parent
HOME = Path.home()

DB_PATH = HOME / "shams_memory.db"
PHOTO_DIR = BASE_DIR / "photos"
PHOTO_DIR.mkdir(exist_ok=True)

TRIG_PIN = 23
ECHO_PIN = 24
PIR_PIN = 22

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
CREDENTIALS_FILE = BASE_DIR / "credentials.json"
TOKEN_FILE = BASE_DIR / "token.json"

STORY_TEXT = """
Do you want a story?

Not a fairy tale...

A real one.

There was once a world full of people who were always okay.

They smiled when they were tired.
They said I am fine when they were not.
And they slowly learned how to disappear... without ever leaving.

No one noticed, because everyone was doing the same.

They did not break loudly.
They broke quietly.

Inside their routines.
Inside their silence.
Inside their screens.

And the most painful part?

They kept thinking they were the only ones feeling this way.

So they stayed busy.

Not to live...
but to avoid thinking.

Because thinking was heavier than sadness.

And one day...

someone asked a simple question:

Are you really okay... or just used to saying it?

And everything... stopped for a moment.

Maybe the truth is not that people are broken.

But that no one taught them how to pause...
without feeling guilty.
""".strip()

try:
    from fusion_hat.tts import Piper
except Exception as e:
    print("[FATAL] fusion_hat TTS not installed or broken")
    print(e)
    sys.exit(1)

try:
    from gpiozero import DistanceSensor, MotionSensor
except Exception:
    DistanceSensor = None
    MotionSensor = None

try:
    from brain import ShamsBrain
except Exception:
    ShamsBrain = None


class Memory:
    def __init__(self, path):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.init_db()

    def init_db(self):
        c = self.conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY,
            task TEXT,
            done INTEGER DEFAULT 0
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS chat (
            id INTEGER PRIMARY KEY,
            role TEXT,
            text TEXT,
            time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        self.conn.commit()

    def add_task(self, task):
        self.conn.execute("INSERT INTO tasks(task) VALUES(?)", (task,))
        self.conn.commit()

    def get_tasks(self):
        return self.conn.execute("SELECT id, task FROM tasks WHERE done=0").fetchall()

    def finish_task(self):
        tasks = self.get_tasks()
        if not tasks:
            return False
        self.conn.execute("UPDATE tasks SET done=1 WHERE id=?", (tasks[0]["id"],))
        self.conn.commit()
        return True

    def save_chat(self, role, text):
        self.conn.execute(
            "INSERT INTO chat(role, text) VALUES(?, ?)",
            (role, text),
        )
        self.conn.commit()

    def recent_context(self, limit=8):
        rows = self.conn.execute(
            "SELECT role, text FROM chat ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()

        context = []
        for row in reversed(rows):
            if row["role"] in ["user", "assistant"]:
                context.append({"role": row["role"], "content": row["text"]})
        return context


class Camera:
    def __init__(self):
        self.command = self.find_camera_command()

    def exists(self, cmd):
        return subprocess.run(
            ["which", cmd],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode == 0

    def find_camera_command(self):
        for cmd in ["rpicam-still", "libcamera-still"]:
            if self.exists(cmd):
                return cmd
        return None

    def take_photo(self):
        if not self.command:
            raise RuntimeError("No camera command found. Install rpicam-apps.")

        filename = datetime.datetime.now().strftime("photo_%Y%m%d_%H%M%S.jpg")
        path = PHOTO_DIR / filename

        subprocess.run(
            [self.command, "-o", str(path), "--timeout", "1200", "--nopreview"],
            check=True,
        )
        return path

    def show_in_terminal(self, path):
        if self.exists("chafa"):
            subprocess.run(["chafa", str(path)], check=False)
        else:
            print(f"[PHOTO] Saved: {path}")


class BodySensors:
    def __init__(self):
        self.distance = None
        self.motion = None

        if DistanceSensor is not None:
            try:
                self.distance = DistanceSensor(echo=ECHO_PIN, trigger=TRIG_PIN, max_distance=4)
                print("[OK] Ultrasonic sensor loaded")
            except Exception as e:
                print("[WARN] Ultrasonic sensor not ready:", e)

        if MotionSensor is not None:
            try:
                self.motion = MotionSensor(PIR_PIN)
                print("[OK] PIR sensor loaded")
            except Exception as e:
                print("[WARN] PIR sensor not ready:", e)

    def measure_distance_cm(self):
        if self.distance is None:
            raise RuntimeError("Ultrasonic sensor not available.")

        readings = []
        for _ in range(7):
            cm = self.distance.distance * 100
            if 2 <= cm <= 400:
                readings.append(cm)

        if not readings:
            raise RuntimeError("No echo received from ultrasonic sensor.")

        readings.sort()
        return readings[len(readings) // 2]

    def describe_position(self):
        cm = self.measure_distance_cm()

        if cm < 40:
            place = "very close to me"
        elif cm < 100:
            place = "close to me"
        elif cm < 180:
            place = "in front of me"
        elif cm < 300:
            place = "a bit far from me"
        else:
            place = "far away from me"

        if self.motion is None:
            motion_text = "The PIR motion sensor is not available."
        elif self.motion.motion_detected:
            motion_text = "I also detect movement."
        else:
            motion_text = "I do not detect movement right now."

        return f"You are about {cm:.0f} centimeters away, standing {place}. {motion_text}"


class GmailReader:
    def __init__(self):
        self.service = None

    def connect(self):
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
        except Exception as e:
            raise RuntimeError(f"Gmail libraries missing: {e}")

        creds = None

        if TOKEN_FILE.exists():
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not CREDENTIALS_FILE.exists():
                    raise RuntimeError("credentials.json not found in this folder.")
                flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
                creds = flow.run_local_server(port=0)

            TOKEN_FILE.write_text(creds.to_json())

        self.service = build("gmail", "v1", credentials=creds)

    def check_unread(self, limit=5):
        if self.service is None:
            self.connect()

        result = self.service.users().messages().list(
            userId="me",
            q="is:unread",
            maxResults=limit,
        ).execute()

        messages = result.get("messages", [])
        if not messages:
            return "You have no unread emails."

        emails = []
        for msg in messages:
            data = self.service.users().messages().get(
                userId="me",
                id=msg["id"],
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()

            headers = data.get("payload", {}).get("headers", [])
            info = {"From": "Unknown sender", "Subject": "No subject", "Date": ""}

            for h in headers:
                if h["name"] in info:
                    info[h["name"]] = h["value"]

            emails.append(f"From {info['From']}. Subject: {info['Subject']}")

        return "You have unread emails. " + " | ".join(emails)


class Shams:
    def __init__(self):
        print("=" * 50)
        print("        SHAMS AI ASSISTANT")
        print("=" * 50)

        self.running = True
        self.motion_cooldown = 60
        self.last_motion_alert = 0

        self.oled = ShamsOLED()
        self.oled.start()

        self.memory = Memory(DB_PATH)

        self.tts = Piper()
        self.tts.set_model("en_US-lessac-low")
        print("[OK] TTS loaded")

        self.stt = HatSTT(gain_db=20)
        print("[OK] Fusion HAT mic loaded with boosted Vosk STT")

        self.camera = Camera()
        self.gmail = GmailReader()
        self.sensors = BodySensors()

        self.telegram = TelegramNotifier()
        if self.telegram.enabled:
            print("[OK] Telegram notifications enabled")
        else:
            print("[WARN] Telegram notifications disabled")

        if ShamsBrain is not None:
            self.brain = ShamsBrain(model="qwen2.5:3b")
            print("[OK]", self.brain.status())
        else:
            self.brain = None
            print("[WARN] brain.py not found. Ollama replies disabled.")

        self.uipath = UiPathBridge(self.handle_uipath_event)
        self.uipath.start()

        self.start_motion_watch()
        print("\n[READY] Shams is online\n")

    def speak(self, text):
        print(f"\n[Shams] {text}")

        try:
            self.oled.set_speaking(True)
        except Exception:
            pass

        try:
            self.tts.say(text)
        except Exception as e:
            print("[TTS ERROR]", e)

        try:
            self.oled.set_speaking(False)
        except Exception:
            pass

    def normalize_text(self, text):
        fixed = text.lower().strip()

        replacements = {
            "hello shows": "hello shams",
            "hello shares": "hello shams",
            "hello show": "hello shams",
            "shows": "shams",
            "shares": "shams",
            "show": "shams",
            "take for of me": "take a photo of me",
            "take four of me": "take a photo of me",
            "take far of me": "take a photo of me",
            "take photo me": "take a photo of me",
            "take a foe of me": "take a photo of me",
            "take a full of me": "take a photo of me",
            "take a pitcher": "take a picture",
            "take picture": "take a picture",
            "check my mail": "check my email",
        }

        for wrong, right in replacements.items():
            fixed = fixed.replace(wrong, right)

        return fixed

    def listen(self):
        print("\n[Listening...]")
        try:
            text = self.stt.listen_once(seconds=5)
            text = self.normalize_text(text)
            print("[Heard]", text)
            return text
        except Exception as e:
            print("[STT ERROR]", e)
            return ""

    def start_motion_watch(self):
        if self.sensors.motion is None:
            print("[WARN] PIR motion watch disabled")
            return

        threading.Thread(target=self.motion_watch_loop, daemon=True).start()
        print("[OK] Motion watch started")

    def motion_watch_loop(self):
        last_state = False

        while self.running:
            try:
                current = self.sensors.motion.motion_detected

                if current and not last_state:
                    now = time.time()
                    if now - self.last_motion_alert >= self.motion_cooldown:
                        self.last_motion_alert = now
                        self.handle_motion_detected()

                last_state = current
                time.sleep(0.5)

            except Exception as e:
                print("[MOTION ERROR]", e)
                time.sleep(2)

    def handle_motion_detected(self):
        print("[MOTION] Motion detected.")

        try:
            self.speak("Motion detected.")
        except Exception as e:
            print("[MOTION TTS ERROR]", e)

        try:
            path = self.camera.take_photo()
            print(f"[MOTION PHOTO] Saved: {path}")

            if self.telegram.enabled:
                self.telegram.send_photo(
                    path,
                    caption="Motion detected. Shams took this photo.",
                )
        except Exception as e:
            print("[MOTION PHOTO ERROR]", e)

            if self.telegram.enabled:
                self.telegram.send(f"Motion detected, but photo failed: {e}")

    def handle_uipath_event(self, event):
        print("[UIPATH EVENT]", event)

        event_name = event.get("event", "unknown")
        message = event.get("message", "")
        level = event.get("level", "info")

        if message:
            reply = message
        else:
            prompt = (
                f"UiPath detected an event.\n"
                f"Event: {event_name}\n"
                f"Level: {level}\n"
                f"Respond as Shams in one short, deep, calm sentence."
            )

            if self.brain is not None:
                reply = self.brain.respond(prompt, context=self.memory.recent_context(limit=6))
            else:
                reply = f"UiPath detected {event_name}."

        self.memory.save_chat("uipath", str(event))
        self.memory.save_chat("assistant", reply)

        self.speak(reply)

        if self.telegram.enabled:
            self.telegram.send(f"UiPath event: {event_name}\n{reply}")

    def take_photo_for_user(self):
        try:
            path = self.camera.take_photo()
            print(f"[PHOTO] Saved: {path}")
            self.camera.show_in_terminal(path)

            if self.telegram.enabled:
                self.telegram.send_photo(path, caption="Shams took a photo for you.")

            return f"I took a photo of you. It is saved as {path.name}."
        except Exception as e:
            return f"I could not take a photo. {e}"

    def check_email(self):
        try:
            reply = self.gmail.check_unread()
            if self.telegram.enabled:
                self.telegram.send(reply)
            return reply
        except Exception as e:
            return f"I could not check Gmail. {e}"

    def check_distance(self):
        try:
            return self.sensors.describe_position()
        except Exception as e:
            return f"I could not measure your distance. {e}"

    def ask_brain(self, text):
        if self.brain is None:
            return f"You said: {text}"

        context = self.memory.recent_context(limit=8)
        return self.brain.respond(text, context=context)

    def think(self, text):
        t = text.lower()

        if "story" in t:
            return STORY_TEXT

        if "exit" in t or "quit" in t or "stop system" in t:
            self.running = False
            return "Goodbye."

        if (
            "take a photo" in t
            or "take photo" in t
            or "take a picture" in t
            or "take picture" in t
            or "photo of me" in t
            or "picture of me" in t
        ):
            return self.take_photo_for_user()

        if (
            "far" in t
            or "distance" in t
            or "close" in t
            or "where am i" in t
            or "standing" in t
        ):
            return self.check_distance()

        if "email" in t or "gmail" in t or "mail" in t:
            return self.check_email()

        if "remind me" in t:
            task = t.replace("remind me", "").strip()
            if task:
                self.memory.add_task(task)
                if self.telegram.enabled:
                    self.telegram.send(f"Task saved: {task}")
                return f"Saved task: {task}"

        if "task" in t or "tasks" in t:
            tasks = self.memory.get_tasks()
            if not tasks:
                return "No tasks."
            return ", ".join([x["task"] for x in tasks])

        if "done" in t or "finish task" in t:
            ok = self.memory.finish_task()
            return "Task completed." if ok else "No tasks."

        if "time" in t:
            return datetime.datetime.now().strftime("%H:%M")

        if "date" in t:
            return datetime.datetime.now().strftime("%Y-%m-%d")

        if "help" in t:
            return (
                "Try: story, take a photo of me, how far am I, check my email, "
                "remind me, my tasks, done, time, date, or exit."
            )

        return self.ask_brain(text)

    def run(self):
        self.speak(f"Hello. I am {NAME}.")

        if self.telegram.enabled:
            self.telegram.send("Shams AI is online.")

        try:
            while self.running:
                input("\nPress ENTER to talk...")

                text = self.listen()
                if not text:
                    continue

                print("[You]", text)
                self.memory.save_chat("user", text)

                reply = self.think(text)

                self.memory.save_chat("assistant", reply)
                self.speak(reply)

        except KeyboardInterrupt:
            print("\n[SHUTDOWN] Ctrl+C received")

        finally:
            self.running = False
            self.speak("System off.")
            self.oled.stop()


if __name__ == "__main__":
    Shams().run()
