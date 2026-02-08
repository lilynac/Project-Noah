# service.py
from __future__ import annotations

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict

# Noah 本体から必要なものを import
import importlib

Noah = importlib.import_module(__package__ + ".Noah")

generate_reply = Noah.generate_reply
normalize_input = Noah.normalize_input
detect_stop_signal = Noah.detect_stop_signal
save_log = Noah.save_log
ui_emit = Noah.ui_emit
log_error = Noah.log_error
mute_initiative = Noah.mute_initiative
INITIATIVE_MUTE_SECONDS = Noah.INITIATIVE_MUTE_SECONDS
ipc_begin = Noah.ipc_begin
ipc_end = Noah.ipc_end
note_user_activity = Noah.note_user_activity

# menubar側と合わせる（必要なら変更）
HOST = "127.0.0.1"
PORT = 8765


class NoahIPCHandler(BaseHTTPRequestHandler):
    # 標準のHTTPログがうるさいなら有効化（Sprint2の「うるさくない」寄り）
    # def log_message(self, format, *args):
    #     return

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        try:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            # BrokenPipe 等でも落ちない
            log_error("IPC_SEND", e, {"path": getattr(self, "path", None)})
            return

    def _read_json(self) -> Dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except Exception as e:
            log_error("IPC_READ", e, {"reason": "bad content-length"})
            raise

        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception as e:
            log_error(
                "IPC_BAD_JSON",
                e,
                {
                    "raw_preview": raw[:80].decode("utf-8", errors="replace"),
                    "path": getattr(self, "path", None),
                },
            )
            raise

    # ---- 互換: Start/Working用の疎通エンドポイント ----
    def do_GET(self) -> None:
        if self.path in ("/", "/health", "/status"):
            self._send_json(200, {"ok": True, "service": "noah", "ts": time.time()})
            return
        self._send_json(404, {"ok": False, "error": "not found"})

    # ---- 互換: Talk用のPOSTエンドポイントとJSONキー吸収 ----
    def do_POST(self) -> None:
        if self.path not in ("/chat", "/talk"):
            self._send_json(404, {"error": "not found"})
            return

        # ★ D2: IPCのやり取り中は initiative を絶対に出さない
        ipc_begin()
        try:
            try:
                body = self._read_json()
            except Exception:
                self._send_json(400, {"error": "invalid json"})
                return

            raw_msg = body.get("message")
            if raw_msg is None:
                raw_msg = body.get("text")
            if raw_msg is None:
                raw_msg = body.get("input")

            message = normalize_input(str(raw_msg or ""))
            if not message:
                self._send_json(400, {"error": "message is required"})
                return

            # ★ D2: menubar経由でも「ユーザー発話が来た」を必ず記録
            note_user_activity()

            if detect_stop_signal(message):
                reply = "うん、わかった。しばらく静かにしてるね。"
                mute_initiative(INITIATIVE_MUTE_SECONDS, reason="stop_signal_ipc")
                try:
                    save_log(message, reply)
                    ui_emit("SAY", reply, emotion="soft_smile")
                except Exception as e:
                    log_error("UI_EMIT_OR_LOG", e, {"phase": "stop_signal"})
                self._send_json(200, {"reply": reply, "text": reply})
                return

            try:
                reply = generate_reply(message)
            except Exception as e:
                log_error("API_OR_REPLY", e, {"phase": "generate_reply"})
                reply = "……今ちょっと不安定みたい。もう一度だけ、同じ言葉で言って。"

            try:
                save_log(message, reply)
                ui_emit("SAY", reply, emotion="soft_smile")
            except Exception as e:
                log_error("UI_EMIT_OR_LOG", e, {"phase": "normal_reply"})

            self._send_json(200, {"reply": reply, "text": reply})

        finally:
            ipc_end()


def run_http_service(host: str = HOST, port: int = PORT) -> None:
    try:
        httpd = ThreadingHTTPServer((host, port), NoahIPCHandler)
    except OSError as e:
        if getattr(e, "errno", None) == 48:  # macOS: Address already in use
            print(f"[Noah IPC] port {port} already in use; skipping HTTP server")
            return
        raise

    print(f"[Noah IPC] listening on http://{host}:{port}")
    try:
        httpd.serve_forever()
    except Exception as e:
        log_error("IPC_SERVER", e, {"host": host, "port": port})
        return
