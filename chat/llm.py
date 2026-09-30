"""Phần dùng chung cho server.py (chạy local) và api/index.py (Vercel): cấu hình provider, mật khẩu, gọi LLM.

Chỉ dùng thư viện chuẩn của Python.
"""
from __future__ import annotations  # macOS có sẵn Python 3.9, chưa hỗ trợ cú pháp "str | None"

import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
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


load_env(HERE / ".env")  # Trên Vercel không có file này: biến môi trường đặt trong dashboard.
ON_VERCEL = bool(os.environ.get("VERCEL"))
# Trần số token model được sinh (gồm cả phần <think>). Không gửi thì Cloudflare mặc định 256 -> R1 bị cắt giữa chừng.
MAX_TOKENS = int(os.environ.get("CHAT_MAX_TOKENS") or 8192)
LOCK_AFTER_HOURS = float(os.environ.get("CHAT_LOCK_AFTER_HOURS") or 0)
PASSWORD = os.environ.get("CHAT_PASSWORD", "")
SESSION_HOURS = float(os.environ.get("CHAT_SESSION_HOURS") or 12)
COOKIE = "olpai_session"
STARTED_AT = time.time()


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


PROVIDERS = load_providers()


def config_problem() -> str | None:
    if ON_VERCEL and not PASSWORD:
        return "Chưa đặt CHAT_PASSWORD trong Environment Variables của Vercel - chat bị tắt để không lộ key."
    if not PROVIDERS:
        return "Chưa có provider nào được cấu hình (LLM_1_BASE_URL / LLM_1_API_KEY / LLM_1_MODEL ...)"
    return None


# --- Đăng nhập: cookie "<thời điểm đăng nhập>.<chữ ký HMAC>", không cần lưu gì phía server ---
# Khoá ký sinh từ mật khẩu, nên đổi CHAT_PASSWORD là mọi phiên cũ mất hiệu lực.
def _sign(issued: str) -> str:
    key = hashlib.sha256(("olpai-chat:" + PASSWORD).encode()).digest()
    return hmac.new(key, issued.encode(), hashlib.sha256).hexdigest()


def check_password(password: str) -> bool:
    return bool(PASSWORD) and hmac.compare_digest(password.encode(), PASSWORD.encode())


def new_session_cookie(secure: bool) -> str:
    issued = str(int(time.time()))
    attrs = f"Path=/; HttpOnly; SameSite=Strict; Max-Age={int(SESSION_HOURS * 3600)}" + ("; Secure" if secure else "")
    return f"{COOKIE}={issued}.{_sign(issued)}; {attrs}"


def session_start(cookie_header: str | None) -> float | None:
    """Thời điểm đăng nhập nếu cookie hợp lệ; không đặt mật khẩu thì luôn hợp lệ (tính từ lúc bật server)."""
    if not PASSWORD:
        return STARTED_AT
    for part in (cookie_header or "").split(";"):
        name, _, value = part.strip().partition("=")
        issued, _, sig = value.partition(".")
        if name == COOKIE and issued.isdigit() and hmac.compare_digest(sig, _sign(issued)):
            if time.time() - int(issued) < SESSION_HOURS * 3600:
                return float(issued)
    return None


def seconds_left(start: float) -> float | None:
    """Khoá LLM sau N giờ: có mật khẩu thì tính từ lúc mỗi người đăng nhập, không thì từ lúc bật server."""
    if LOCK_AFTER_HOURS <= 0:
        return None
    return max(0.0, start + LOCK_AFTER_HOURS * 3600 - time.time())


def status(start: float) -> dict:
    return {
        "providers": [f"{p['name']} · {p['model']}" for p in PROVIDERS],
        "problem": config_problem(),
        "seconds_left": seconds_left(start),
    }


def open_stream(messages: list) -> tuple[object, dict, list[str]]:
    """Thử lần lượt từng provider; lỗi trước khi bắt đầu stream (hết quota, 429, sai key...) -> chuyển provider kế.

    Trả về (response, provider, danh sách provider bị bỏ qua); tất cả đều lỗi thì raise RuntimeError.
    """
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
            return urllib.request.urlopen(upstream, timeout=300), p, skipped
        except urllib.error.HTTPError as e:
            skipped.append(f"{p['name']}: lỗi {e.code} {e.read().decode(errors='replace')[:300]}")
        except (urllib.error.URLError, TimeoutError) as e:
            skipped.append(f"{p['name']}: không kết nối được ({getattr(e, 'reason', e)})")
    raise RuntimeError("Tất cả provider đều lỗi:\n" + "\n".join(skipped))


def ndjson_lines(resp, p: dict, skipped: list[str]):
    """Chuyển response của provider thành các dòng NDJSON cho trình duyệt: dòng đầu là meta, sau đó {"c", "r"}."""
    def line(obj) -> bytes:
        return (json.dumps(obj, ensure_ascii=False) + "\n").encode()

    yield line({"provider": f"{p['name']} · {p['model']}", "skipped": skipped})
    with resp:
        content_type = resp.headers.get("Content-Type", "")
        if "json" in content_type and "stream" not in content_type:
            # Provider bỏ qua stream=True và trả nguyên 1 cục JSON.
            msg = json.loads(resp.read())["choices"][0]["message"]
            yield line({"c": msg.get("content") or "", "r": msg.get("reasoning_content") or msg.get("reasoning") or ""})
            return
        for raw in resp:
            text = raw.decode("utf-8", errors="replace").strip()
            if not text.startswith("data:"):
                continue
            data = text[5:].strip()
            if data == "[DONE]":
                break
            choices = json.loads(data).get("choices") or []
            if choices:
                delta = choices[0].get("delta") or {}
                content, reasoning = delta.get("content"), delta.get("reasoning_content") or delta.get("reasoning")
                if content or reasoning:
                    yield line({"c": content or "", "r": reasoning or ""})
