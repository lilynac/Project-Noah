# service.py
from __future__ import annotations

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict

# Noah 本体から必要なものを import
from .Noah import (
    generate_reply,
    normalize_input,
    detect_stop_signal,
    save_log,
    ui_emit,
    log_error,
)

# menubar側と合わせる（必要なら変更）
HOST = "127.0.0.1"
PORT = 8765

# D2で本格化するが、D1/D2互換のための最小既定値
INITIATIVE_MUTE_SECONDS = 60


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
        # /chat だけでなく /talk も受ける
        if self.path not in ("/chat", "/talk"):
            self._send_json(404, {"error": "not found"})
            return

        try:
            body = self._read_json()
        except Exception:
            self._send_json(400, {"error": "invalid json"})
            return

        # message / text / input どれでも受ける
        raw_msg = body.get("message")
        if raw_msg is None:
            raw_msg = body.get("text")
        if raw_msg is None:
            raw_msg = body.get("input")

        message = normalize_input(str(raw_msg or ""))
        if not message:
            self._send_json(400, {"error": "message is required"})
            return

        # 「静かに/やめて」系（D2で本格化するが、互換のためここでも吸収）
        if detect_stop_signal(message):
            reply = "うん、わかった。しばらく静かにしてるね。"
            try:
                save_log(message, reply)
                ui_emit("SAY", reply, emotion="soft_smile")
            except Exception as e:
                log_error("UI_EMIT_OR_LOG", e, {"phase": "stop_signal"})
            # 返却キーも互換で両方
            self._send_json(200, {"reply": reply, "text": reply})
            return

        # 通常応答（API失敗でも落ちないのは generate_reply 側で担保）
        try:
            reply = generate_reply(message)
        except Exception as e:
            # generate_reply 側でも握る想定だが、ここでも最後の砦
            log_error("API_OR_REPLY", e, {"phase": "generate_reply"})
            reply = "……今ちょっと不安定みたい。もう一度だけ、同じ言葉で言って。"

        try:
            save_log(message, reply)
            ui_emit("SAY", reply, emotion="soft_smile")
        except Exception as e:
            log_error("UI_EMIT_OR_LOG", e, {"phase": "normal_reply"})

        # 返却キー互換：reply と text を両方返す
        self._send_json(200, {"reply": reply, "text": reply})


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
