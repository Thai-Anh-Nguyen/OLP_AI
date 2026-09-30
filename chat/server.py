"""Trang chat tối giản mô phỏng chatbot LLM của kỳ thi: chỉ text, không upload, không tool.

Chạy:  python3 server.py   rồi mở http://localhost:8000
Chỉ dùng thư viện chuẩn của Python, không cần cài gì. Bản chạy trên Vercel nằm ở api/index.py.
"""
from __future__ import annotations

import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import llm

PORT = int(os.environ.get("CHAT_PORT", "8000"))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def send_json(self, status: int, payload: dict, cookie: str | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict:
        return json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")

    def do_GET(self):
        if self.path == "/":
            body = (llm.HERE / "public" / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/status":
            start = llm.session_start(self.headers.get("Cookie"))
            if start is None:
                self.send_json(401, {"error": "login"})
            else:
                self.send_json(200, llm.status(start))
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/api/login":
            if llm.check_password(str(self.read_json().get("password", ""))):
                self.send_json(200, {"ok": True}, cookie=llm.new_session_cookie(secure=False))
            else:
                time.sleep(1)  # làm chậm việc đoán mật khẩu
                self.send_json(401, {"error": "Sai mật khẩu."})
            return
        if self.path != "/api/chat":
            self.send_error(404)
            return
        start = llm.session_start(self.headers.get("Cookie"))
        if start is None:
            self.send_json(401, {"error": "Phiên đăng nhập đã hết hạn - tải lại trang để đăng nhập."})
            return
        left = llm.seconds_left(start)
        if left is not None and left <= 0:
            self.send_json(403, {"error": "Đã hết thời gian được dùng LLM (giống luật thi: khoá sau giờ thứ 5)."})
            return
        if problem := llm.config_problem():
            self.send_json(500, {"error": problem})
            return

        try:
            resp, p, skipped = llm.open_stream(self.read_json()["messages"])
        except RuntimeError as e:
            self.send_json(502, {"error": str(e)})
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.end_headers()
        try:
            for line in llm.ndjson_lines(resp, p, skipped):
                self.wfile.write(line)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass


if __name__ == "__main__":
    for i, p in enumerate(llm.PROVIDERS, 1):
        print(f"  {i}. {p['name']} · {p['model']}")
    if problem := llm.config_problem():
        print(f"CẢNH BÁO: {problem}")
    print("Cần mật khẩu (CHAT_PASSWORD) để vào chat." if llm.PASSWORD else "Không đặt CHAT_PASSWORD: ai mở được trang là chat được.")
    if llm.LOCK_AFTER_HOURS > 0:
        start = "lúc mỗi người đăng nhập" if llm.PASSWORD else "bây giờ"
        print(f"Chat sẽ tự khoá sau {llm.LOCK_AFTER_HOURS:g} giờ kể từ {start}.")
    print(f"Mở http://localhost:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
