"""Trang chat tối giản mô phỏng chatbot LLM của kỳ thi: chỉ text, không upload, không tool.

Chạy:  python3 server.py   rồi mở http://localhost:8000
Chỉ dùng thư viện chuẩn của Python, không cần cài gì.
"""
from __future__ import annotations  # macOS có sẵn Python 3.9, chưa hỗ trợ cú pháp "str | None"

import json
import os
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


load_env(HERE / ".env")
BASE_URL = os.environ.get("LLM_BASE_URL", "").rstrip("/")
API_KEY = os.environ.get("LLM_API_KEY", "")
MODEL = os.environ.get("LLM_MODEL", "")
PORT = int(os.environ.get("CHAT_PORT", "8000"))
LOCK_AFTER_HOURS = float(os.environ.get("CHAT_LOCK_AFTER_HOURS") or 0)
STARTED_AT = time.time()


def config_problem() -> str | None:
    if not BASE_URL or not API_KEY or not MODEL:
        return "Thiếu LLM_BASE_URL / LLM_API_KEY / LLM_MODEL trong chat/.env"
    if "<ACCOUNT_ID>" in BASE_URL or API_KEY.startswith("your-"):
        return "chat/.env vẫn còn giá trị mẫu - điền Account ID và API key thật"
    return None


def seconds_left() -> float | None:
    if LOCK_AFTER_HOURS <= 0:
        return None
    return max(0.0, STARTED_AT + LOCK_AFTER_HOURS * 3600 - time.time())


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            body = (HERE / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/status":
            self.send_json(200, {"model": MODEL, "problem": config_problem(), "seconds_left": seconds_left()})
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/api/chat":
            self.send_error(404)
            return
        left = seconds_left()
        if left is not None and left <= 0:
            self.send_json(403, {"error": "Đã hết thời gian được dùng LLM (giống luật thi: khoá sau giờ thứ 5)."})
            return
        if problem := config_problem():
            self.send_json(500, {"error": problem})
            return

        messages = json.loads(self.rfile.read(int(self.headers["Content-Length"])))["messages"]
        upstream = urllib.request.Request(
            f"{BASE_URL}/chat/completions",
            data=json.dumps({"model": MODEL, "messages": messages, "stream": True}).encode(),
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
                "User-Agent": "olpai-practice-chat/1.0",
            },
        )
        try:
            resp = urllib.request.urlopen(upstream, timeout=300)
        except urllib.error.HTTPError as e:
            self.send_json(e.code, {"error": f"Provider trả lỗi {e.code}: {e.read().decode(errors='replace')[:1500]}"})
            return
        except urllib.error.URLError as e:
            self.send_json(502, {"error": f"Không kết nối được provider: {e.reason}"})
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.end_headers()
        try:
            with resp:
                if "json" in resp.headers.get("Content-Type", "") and "stream" not in resp.headers.get("Content-Type", ""):
                    # Provider bỏ qua stream=True và trả nguyên 1 cục JSON.
                    msg = json.loads(resp.read())["choices"][0]["message"]
                    self.emit(msg.get("content"), msg.get("reasoning_content") or msg.get("reasoning"))
                    return
                for raw in resp:
                    line = raw.decode("utf-8", errors="replace").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    choices = json.loads(data).get("choices") or []
                    if choices:
                        delta = choices[0].get("delta") or {}
                        self.emit(delta.get("content"), delta.get("reasoning_content") or delta.get("reasoning"))
        except (BrokenPipeError, ConnectionResetError):
            pass

    def emit(self, content, reasoning) -> None:
        if content or reasoning:
            self.wfile.write((json.dumps({"c": content or "", "r": reasoning or ""}, ensure_ascii=False) + "\n").encode())
            self.wfile.flush()


if __name__ == "__main__":
    print(f"Model: {MODEL or '(chưa cấu hình)'}")
    if problem := config_problem():
        print(f"CẢNH BÁO: {problem}")
    if LOCK_AFTER_HOURS > 0:
        print(f"Chat sẽ tự khoá sau {LOCK_AFTER_HOURS:g} giờ kể từ bây giờ.")
    print(f"Mở http://localhost:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
