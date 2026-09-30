"""Trang chat tối giản mô phỏng chatbot LLM của kỳ thi: chỉ text, không upload, không tool.

Chạy:  python3 server.py   rồi mở http://localhost:8000
Chỉ dùng thư viện chuẩn của Python, không cần cài gì.
"""
from __future__ import annotations  # macOS có sẵn Python 3.9, chưa hỗ trợ cú pháp "str | None"

import json
import os
import time
import urllib.error
import urllib.parse
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


def load_providers() -> list[dict]:
    """LLM_1_*, LLM_2_*, ... theo thứ tự ưu tiên; provider thiếu giá trị hoặc còn giá trị mẫu thì bỏ qua."""
    providers = []
    for i in range(1, 10):
        base = os.environ.get(f"LLM_{i}_BASE_URL", "").rstrip("/")
        key = os.environ.get(f"LLM_{i}_API_KEY", "")
        model = os.environ.get(f"LLM_{i}_MODEL", "")
        if not (base and key and model) or "<ACCOUNT_ID>" in base or key.startswith("your-"):
            continue
        name = os.environ.get(f"LLM_{i}_NAME") or urllib.parse.urlparse(base).hostname
        max_tokens = int(os.environ.get(f"LLM_{i}_MAX_TOKENS") or MAX_TOKENS)
        providers.append({"name": name, "base": base, "key": key, "model": model, "max_tokens": max_tokens})
    return providers


load_env(HERE / ".env")
# Trần số token model được sinh (gồm cả phần <think>). Không gửi thì Cloudflare mặc định 256 -> R1 bị cắt giữa chừng.
MAX_TOKENS = int(os.environ.get("CHAT_MAX_TOKENS") or 8192)
PROVIDERS = load_providers()
PORT = int(os.environ.get("CHAT_PORT", "8000"))
LOCK_AFTER_HOURS = float(os.environ.get("CHAT_LOCK_AFTER_HOURS") or 0)
STARTED_AT = time.time()


def config_problem() -> str | None:
    if not PROVIDERS:
        return "Chưa có provider nào được cấu hình trong chat/.env (LLM_1_BASE_URL / LLM_1_API_KEY / LLM_1_MODEL ...)"
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
            self.send_json(200, {
                "providers": [f"{p['name']} · {p['model']}" for p in PROVIDERS],
                "problem": config_problem(),
                "seconds_left": seconds_left(),
            })
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
        # Thử lần lượt từng provider; lỗi trước khi bắt đầu stream (hết quota, 429, sai key...) -> chuyển provider kế.
        skipped = []
        for p in PROVIDERS:
            upstream = urllib.request.Request(
                f"{p['base']}/chat/completions",
                data=json.dumps({"model": p["model"], "messages": messages, "stream": True, "max_tokens": p["max_tokens"]}).encode(),
                headers={
                    "Authorization": f"Bearer {p['key']}",
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream",
                    "User-Agent": "olpai-practice-chat/1.0",
                },
            )
            try:
                resp = urllib.request.urlopen(upstream, timeout=300)
                break
            except urllib.error.HTTPError as e:
                skipped.append(f"{p['name']}: lỗi {e.code} {e.read().decode(errors='replace')[:300]}")
            except (urllib.error.URLError, TimeoutError) as e:
                skipped.append(f"{p['name']}: không kết nối được ({getattr(e, 'reason', e)})")
        else:
            self.send_json(502, {"error": "Tất cả provider đều lỗi:\n" + "\n".join(skipped)})
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.end_headers()
        try:
            meta = {"provider": f"{p['name']} · {p['model']}", "skipped": skipped}
            self.wfile.write((json.dumps(meta, ensure_ascii=False) + "\n").encode())
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
    for i, p in enumerate(PROVIDERS, 1):
        print(f"  {i}. {p['name']} · {p['model']}")
    if problem := config_problem():
        print(f"CẢNH BÁO: {problem}")
    if LOCK_AFTER_HOURS > 0:
        print(f"Chat sẽ tự khoá sau {LOCK_AFTER_HOURS:g} giờ kể từ bây giờ.")
    print(f"Mở http://localhost:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
