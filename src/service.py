# service.py
from __future__ import annotations

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict

# Noah 本体から必要なものを import
import importlib

Noah = importlib.import_module(__package__ + ".Noah")

from .noah_config import load_runtime_config
from .log_setup import get_logger

_CFG = load_runtime_config()
_SLOG = get_logger(
    component="ipc",
    log_dir=_CFG.log_dir,
    level=_CFG.log_level,
    max_bytes=_CFG.log_max_bytes,
    backup_count=_CFG.log_backup_count,
)

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
    def _client_ip(self) -> str:
        try:
            return str(self.client_address[0])
        except Exception:
            return "unknown"


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
        path = getattr(self, "path", "")
        _SLOG.info("IPC_GET_BEGIN path=%s ip=%s", path, self._client_ip())

        if path in ("/", "/health", "/status"):
            _SLOG.info("IPC_GET_OK path=%s ip=%s", path, self._client_ip())
            self._send_json(200, {"ok": True, "service": "noah", "ts": time.time()})
            return

        _SLOG.info("IPC_GET_404 path=%s ip=%s", path, self._client_ip())
        self._send_json(404, {"ok": False, "error": "not found"})

    # ---- 互換: Talk用のPOSTエンドポイントとJSONキー吸収 ----
    def do_POST(self) -> None:
        path = getattr(self, "path", "")
        ip = self._client_ip()
        _SLOG.info("IPC_POST_BEGIN path=%s ip=%s", path, ip)

        if path not in ("/chat", "/talk"):
            _SLOG.info("IPC_POST_404 path=%s ip=%s", path, ip)
            self._send_json(404, {"error": "not found"})
            return

        # ★ D2: IPCのやり取り中は initiative を絶対に出さない
        ipc_begin()
        try:
            try:
                body = self._read_json()
            except Exception:
                _SLOG.info("IPC_POST_400_BAD_JSON path=%s ip=%s", path, ip)
                self._send_json(400, {"error": "invalid json"})
                return

            raw_msg = body.get("message")
            if raw_msg is None:
                raw_msg = body.get("text")
            if raw_msg is None:
                raw_msg = body.get("input")

            message = normalize_input(str(raw_msg or ""))
            if not message:
                _SLOG.info("IPC_POST_400_EMPTY_MESSAGE path=%s ip=%s", path, ip)
                self._send_json(400, {"error": "message is required"})
                return

            _SLOG.info("IPC_POST_MESSAGE path=%s ip=%s msg_len=%s", path, ip, len(message))

            # ★ D2: menubar経由でも「ユーザー発話が来た」を必ず記録
            note_user_activity()

            # ★ D3-3: 状態表示（Thinking）
            try:
                ui_emit("STATE", "THINKING", emotion="neutral")
            except Exception:
                pass

            if detect_stop_signal(message):
                reply = "うん、わかった。しばらく静かにしてるね。"
                _SLOG.info("IPC_POST_STOP_SIGNAL path=%s ip=%s mute_sec=%s", path, ip, INITIATIVE_MUTE_SECONDS)

                mute_initiative(INITIATIVE_MUTE_SECONDS, reason="stop_signal_ipc")
                try:
                    save_log(message, reply)
                    ui_emit("SAY", reply, emotion="soft_smile")
                    # ★ D3-3: 状態表示（Readyへ復帰）
                    ui_emit("STATE", "READY", emotion="neutral")
                except Exception as e:
                    log_error("UI_EMIT_OR_LOG", e, {"phase": "stop_signal"})
                    _SLOG.exception("IPC_POST_STOP_SIGNAL_SIDE_EFFECT_FAIL path=%s ip=%s", path, ip)

                self._send_json(200, {"reply": reply, "text": reply})
                _SLOG.info("IPC_POST_END path=%s ip=%s status=200 reply_len=%s", path, ip, len(reply))
                return

            ok = True
            try:
                reply = generate_reply(message)
            except Exception as e:
                ok = False
                log_error("API_OR_REPLY", e, {"phase": "generate_reply"})
                _SLOG.exception("IPC_POST_GENERATE_REPLY_FAIL path=%s ip=%s", path, ip)
                reply = "……今ちょっと不安定みたい。もう一度だけ、同じ言葉で言って。"

            # ★ D3-2: 代替応答文を“エラー扱い”に落とす（推定なし・再現性100%）
            FALLBACK_REPLY = "……今ちょっと不安定みたい。もう一度だけ、同じ言葉で言って。"
            if reply.strip() == FALLBACK_REPLY:
                ok = False

            # ★ D3-2: EMO安定（成功/失敗で固定）
            say_emo = "soft_smile" if ok else "concerned"

            try:
                save_log(message, reply)
                ui_emit("SAY", reply, emotion=say_emo)

                # ★ D3-3: 状態表示（成功→READY / 失敗→ERROR）
                if ok:
                    ui_emit("STATE", "READY", emotion="neutral")
                else:
                    # Sprint3仕上げ：Error理由（固定短文）をpayloadで渡す（推定禁止・イベント駆動）
                    # payload内フォーマット: "ERROR\t<reason>\t<log_dir>"
                    reason = "API error"
                    log_dir = getattr(_CFG, "log_dir", "")
                    ui_emit("STATE", f"ERROR\t{reason}\t{log_dir}", emotion="concerned")
            except Exception as e:
                log_error("UI_EMIT_OR_LOG", e, {"phase": "normal_reply"})
                _SLOG.exception("IPC_POST_REPLY_SIDE_EFFECT_FAIL path=%s ip=%s", path, ip)

            self._send_json(200, {"reply": reply, "text": reply})
            _SLOG.info("IPC_POST_END path=%s ip=%s status=200 reply_len=%s", path, ip, len(reply))


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
