import rumps
import subprocess
import sys
from pathlib import Path
import json
import time
import urllib.request
import urllib.error
from src.paths import UI_QUEUE_PATH


# ===== Paths / Logs =====
THIS_FILE = Path(__file__).resolve()

# noah_menubar.py を src/ に置く想定
# 例: /Users/you/Noah/src/noah_menubar.py
# プロジェクトルートはその親: /Users/you/Noah
PROJECT_ROOT = THIS_FILE.parent.parent

LOG_DIR = Path.home() / "Library" / "Logs" / "Noah"
LOG_DIR.mkdir(parents=True, exist_ok=True)
BACKEND_LOG = LOG_DIR / "menubar_backend.log"


SERVICE_URL = "http://127.0.0.1:8765"
CHAT_URL = SERVICE_URL + "/chat"
HEALTH_URL = SERVICE_URL + "/health"

def ui_emit(etype: str, payload: str, emotion: str = "neutral"):
    """
    Overlay（desktop_noah.py）が監視している ui_queue.txt へイベントを追記する。
    フォーマット: TYPE\tEMOTION\tPAYLOAD
    ※Sprint3の範囲：表示だけ（推定なし・イベント駆動）
    """
    try:
        UI_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(UI_QUEUE_PATH, "a", encoding="utf-8") as f:
            f.write(f"{etype}\t{emotion}\t{payload}\n")
    except Exception:
        # menubarは落とさない
        return


def ui_error(reason: str):
    """
    Error理由（固定短文）＋ログ場所を payload で渡す。
    payloadフォーマット: "ERROR\t<reason>\t<log_dir>"
    """
    ui_emit("STATE", f"ERROR\t{reason}\t{LOG_DIR}", emotion="concerned")

def http_get(url: str, timeout: float = 0.25) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read().decode("utf-8")

def http_post_json(url: str, payload: dict, timeout: float = 60.0) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)

def is_service_alive() -> bool:
    try:
        raw = http_get(HEALTH_URL, timeout=0.2)
        obj = json.loads(raw)
        return bool(obj.get("ok"))
    except Exception:
        return False


# ===== MenuBar App =====
class NoahMenu(rumps.App):
    def __init__(self):
        super().__init__(
            "Noah",
            menu=[
                "Talk...",
                None,
                "Start",
                "Stop",
                None,
                "Open Logs",
                "Quit",
            ],
            quit_button=None,
        )
        self.proc = None
        self.busy = False
        self.set_status("Idle")

    def set_status(self, s: str):
        # menubarの表示名
        self.title = f"Noah · {s}"

    def is_running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    # --- Talk (one-shot) ---
    @rumps.clicked("Talk...")
    def talk(self, _):
        if self.busy:
            return

        w = rumps.Window(
            title="Talk to Noah",
            message="メッセージを入力してね",
            default_text="",
            ok="Send",
            cancel="Cancel",
            dimensions=(360, 140),
        )
        r = w.run()
        if not r.clicked:
            return

        user_text = (r.text or "").strip()
        if not user_text:
            return

        self.busy = True
        self.set_status("Thinking")
        ui_emit("STATE", "THINKING", emotion="neutral")

        try:
            # もし常駐がいなければ起動して待つ
            if not is_service_alive():
                self.start(None)
                for _ in range(30):
                    if is_service_alive():
                        break
                    time.sleep(0.1)

            if not is_service_alive():
                self.set_status("Error")
                ui_error("Service not reachable")
                rumps.alert("Noah (error)", f"Service not reachable\nLog: {LOG_DIR}")
                return


            obj = http_post_json(CHAT_URL, {"message": user_text}, timeout=60.0)
            reply = (obj.get("reply") or "").strip() or "(no reply)"
            rumps.alert("Noah", reply[-1400:])

        except urllib.error.HTTPError as e:
            # HTTPエラー：menubar側では「次の行動」が分かる固定短文に寄せる（推定なし）
            ui_error("Unknown error")
            body = e.read().decode("utf-8", errors="ignore")
            rumps.alert("Noah (error)", f"Unknown error\nHTTP {e.code}\nLog: {LOG_DIR}\n\n{body}"[-1400:])

        except urllib.error.URLError as e:
            # タイムアウト等はURLErrorに来ることがある
            ui_error("Timeout")
            rumps.alert("Noah (error)", f"Timeout\nLog: {LOG_DIR}\n\n{repr(e)}"[-1400:])

        except Exception as e:
            ui_error("Unknown error")
            rumps.alert("Noah (error)", f"Unknown error\nLog: {LOG_DIR}\n\n{repr(e)}"[-1400:])
        finally:
            self.busy = False
            alive = is_service_alive()
            self.set_status("Ready" if alive else "Idle")
            if alive:
                ui_emit("STATE", "READY", emotion="neutral")
            else:
                # Idleはoverlay上はReady扱いでも良いが、ここは無理にERRORにしない（表示だけ最小）
                ui_emit("STATE", "READY", emotion="neutral")


    # --- Start (service mode) ---
    @rumps.clicked("Start")
    def start(self, _):
        if self.is_running():
            # すでにプロセス管理下で動いてるなら、状態だけ整える
            self.set_status("Ready" if is_service_alive() else "Working")
            return

        self.set_status("Working")
        f = open(BACKEND_LOG, "a", buffering=1)

        try:
            self.proc = subprocess.Popen(
                [sys.executable, "-u", "-m", "src", "--service"],
                stdout=f,
                stderr=f,
                stdin=subprocess.DEVNULL,
                cwd=str(PROJECT_ROOT),
            )
        except Exception as e:
            self.set_status("Error")
            rumps.alert("Noah (error)", repr(e))
            return

        # 起動待ちして Ready にする（最大6秒）
        for _ in range(60):
            if is_service_alive():
                self.set_status("Ready")
                return
            time.sleep(0.1)

        # まだ立ち上がってない（遅い or 起動失敗の可能性）
        self.set_status("Working")


    # --- Stop ---
    @rumps.clicked("Stop")
    def stop(self, _):
        if self.is_running():
            try:
                self.proc.terminate()
            except Exception:
                pass
        self.proc = None
        self.set_status("Idle")

    # --- Open Logs ---
    @rumps.clicked("Open Logs")
    def open_logs(self, _):
        subprocess.Popen(["open", str(LOG_DIR)])

    # --- Quit ---
    @rumps.clicked("Quit")
    def quit_app(self, _):
        self.stop(None)
        rumps.quit_application()


if __name__ == "__main__":
    NoahMenu().run()
