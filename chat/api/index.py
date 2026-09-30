"""Bản chạy trên Vercel của server.py: một ASGI app xử lý /api/status, /api/login, /api/chat.

vercel.json chuyển mọi /api/<route> về file này kèm ?route=<route>. Chỉ dùng thư viện chuẩn.
"""
from __future__ import annotations

import asyncio
import json
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import llm  # noqa: E402


async def read_body(receive) -> dict:
    body = b""
    while True:
        event = await receive()
        body += event.get("body", b"")
        if not event.get("more_body"):
            return json.loads(body or b"{}")


async def send_json(send, status: int, payload: dict, cookie: str | None = None) -> None:
    headers = [(b"content-type", b"application/json; charset=utf-8"), (b"cache-control", b"no-store")]
    if cookie:
        headers.append((b"set-cookie", cookie.encode()))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": json.dumps(payload, ensure_ascii=False).encode()})


async def app(scope, receive, send):
    if scope["type"] != "http":
        return
    query = urllib.parse.parse_qs(scope.get("query_string", b"").decode())
    route = (query.get("route") or [scope["path"].rstrip("/").rsplit("/", 1)[-1]])[0]
    method = scope["method"]
    cookie = next((v.decode() for k, v in scope["headers"] if k == b"cookie"), None)

    if route == "login" and method == "POST":
        if llm.check_password(str((await read_body(receive)).get("password", ""))):
            await send_json(send, 200, {"ok": True}, cookie=llm.new_session_cookie(secure=True))
        else:
            await asyncio.sleep(1)  # làm chậm việc đoán mật khẩu
            await send_json(send, 401, {"error": "Sai mật khẩu."})
        return

    start = llm.session_start(cookie)
    if route == "status" and method == "GET":
        await send_json(send, 401, {"error": "login"}) if start is None else await send_json(send, 200, llm.status(start))
        return
    if route != "chat" or method != "POST":
        await send_json(send, 404, {"error": "Not found"})
        return
    if start is None:
        await send_json(send, 401, {"error": "Phiên đăng nhập đã hết hạn - tải lại trang để đăng nhập."})
        return
    left = llm.seconds_left(start)
    if left is not None and left <= 0:
        await send_json(send, 403, {"error": "Đã hết thời gian được dùng LLM (giống luật thi: khoá sau giờ thứ 5)."})
        return
    if problem := llm.config_problem():
        await send_json(send, 500, {"error": problem})
        return

    messages = (await read_body(receive))["messages"]
    try:
        # urllib là blocking -> chạy trong thread để không chặn các request khác trên cùng instance.
        resp, p, skipped = await asyncio.to_thread(llm.open_stream, messages)
    except RuntimeError as e:
        await send_json(send, 502, {"error": str(e)})
        return
    await send({"type": "http.response.start", "status": 200, "headers": [
        (b"content-type", b"application/x-ndjson; charset=utf-8"),
        (b"cache-control", b"no-store"),
        (b"x-accel-buffering", b"no"),
    ]})
    lines = llm.ndjson_lines(resp, p, skipped)
    while (line := await asyncio.to_thread(next, lines, None)) is not None:
        await send({"type": "http.response.body", "body": line, "more_body": True})
    await send({"type": "http.response.body", "body": b""})
