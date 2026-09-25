"""Exercise real HTTP requests without loading the LLM or personal state."""
import importlib.util
import json
import logging
import sys
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread
from types import ModuleType
from unittest.mock import Mock

import pytest

from src import log_setup


@pytest.fixture
def ipc(monkeypatch):
    noah = ModuleType("src.Noah")
    for name in (
        "generate_reply", "normalize_input", "detect_stop_signal", "save_log",
        "ui_emit", "log_error", "mute_initiative", "ipc_begin", "ipc_end",
        "note_user_activity",
    ):
        setattr(noah, name, Mock())
    noah.generate_reply.return_value = "おかえり。"
    noah.normalize_input.side_effect = str.strip
    noah.detect_stop_signal.return_value = False
    noah.INITIATIVE_MUTE_SECONDS = 60
    monkeypatch.setitem(sys.modules, "src.Noah", noah)
    monkeypatch.setattr(log_setup, "get_logger", lambda **kwargs: logging.getLogger("test.ipc"))
    spec = importlib.util.spec_from_file_location(
        "src._service_test", Path(__file__).resolve().parents[1] / "src" / "service.py"
    )
    service = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(service)
    request_finished = Event()

    class FinishedHandler(service.NoahIPCHandler):
        def finish(self):
            try:
                super().finish()
            finally:
                request_finished.set()

    server = ThreadingHTTPServer(("127.0.0.1", 0), FinishedHandler)
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
    thread.start()

    def post(body, path="/chat"):
        request_finished.clear()
        connection = HTTPConnection(*server.server_address, timeout=2)
        try:
            connection.request("POST", path, body, {"Content-Type": "application/json"})
            response = connection.getresponse()
            payload = json.loads(response.read())
            # Receiving bytes does not imply do_POST's finally block has run.
            assert request_finished.wait(5), "HTTP handler did not finish"
            return response.status, payload
        finally:
            connection.close()

    try:
        yield post, noah
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


@pytest.mark.parametrize("body", ["[]", "null", '"hello"', "42", "true", "{"])
def test_invalid_json_body_returns_400_without_generating_reply(ipc, body):
    post, noah = ipc
    status, payload = post(body)
    assert status == 400
    assert "error" in payload
    noah.generate_reply.assert_not_called()
    noah.note_user_activity.assert_not_called()
    noah.ipc_begin.assert_called_once()
    noah.ipc_end.assert_called_once()


@pytest.mark.parametrize("key", ["message", "text", "input"])
@pytest.mark.parametrize("value", [123, True, [], {}, ["hello"]])
def test_non_string_message_is_rejected(ipc, key, value):
    post, noah = ipc
    status, payload = post(json.dumps({key: value}))
    assert status == 400
    assert payload == {"error": "message must be a string"}
    noah.generate_reply.assert_not_called()
    noah.note_user_activity.assert_not_called()
    noah.ipc_end.assert_called_once()


@pytest.mark.parametrize("body", [{}, {"message": None}, {"message": "  "}])
def test_missing_message_is_rejected(ipc, body):
    post, noah = ipc
    assert post(json.dumps(body)) == (400, {"error": "message is required"})
    noah.generate_reply.assert_not_called()
    noah.ipc_end.assert_called_once()


@pytest.mark.parametrize("path", ["/chat", "/talk"])
@pytest.mark.parametrize("key", ["message", "text", "input"])
def test_supported_routes_and_keys_preserve_reply(ipc, path, key):
    post, noah = ipc
    assert post(json.dumps({key: "  ただいま  "}), path) == (
        200, {"reply": "おかえり。", "text": "おかえり。"}
    )
    noah.generate_reply.assert_called_once_with("ただいま")
    noah.note_user_activity.assert_called_once()
    noah.ipc_end.assert_called_once()


def test_null_key_falls_back_to_compatible_alias(ipc):
    post, noah = ipc
    assert post(json.dumps({"message": None, "text": "hello"}))[0] == 200
    noah.generate_reply.assert_called_once_with("hello")


def test_server_accepts_valid_request_after_invalid_body(ipc):
    post, noah = ipc
    assert post("[]")[0] == 400
    assert post(json.dumps({"message": "hello"}))[0] == 200
    assert noah.ipc_begin.call_count == noah.ipc_end.call_count == 2
