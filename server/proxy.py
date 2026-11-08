"""Shadow Cursor cloud (Aiven application): the website, the Mac app download, and the API keys.

The app on a juror's Mac holds no keys: it calls /api/holo, /api/openai, /api/linkup and
/api/gladia here with the app token, and this server forwards the request with the real key.

    PORT=8080 HAI_API_KEY=… OPENAI_API_KEY=… LINKUP_API_KEY=… GLADIA_API_KEY=… python proxy.py
"""

import os
import time
from pathlib import Path

from aiohttp import ClientSession, ClientTimeout, web

HERE = Path(__file__).parent
TOKEN = os.environ.get("SHADOW_APP_TOKEN", "shadow-cursor-jury")
DAILY_CAP = int(os.environ.get("SHADOW_DAILY_CAP", "6000"))  # calls per day, all jurors together
# name → (upstream URL, key env var, header that carries the key)
UPSTREAM = {
    "holo": ("https://api.hcompany.ai/v1", "HAI_API_KEY", "Authorization"),
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY", "Authorization"),
    "linkup": ("https://api.linkup.so/v1/search", "LINKUP_API_KEY", "Authorization"),
    "gladia": ("https://api.gladia.io/v2/live", "GLADIA_API_KEY", "x-gladia-key"),
}
usage = {"day": "", "calls": 0}
http: ClientSession | None = None


def authorized(req: web.Request) -> bool:
    sent = req.headers.get("Authorization", "").removeprefix("Bearer ") or req.headers.get("x-gladia-key", "")
    return sent == TOKEN


def under_cap() -> bool:
    day = time.strftime("%Y-%m-%d")
    if usage["day"] != day:
        usage.update(day=day, calls=0)
    usage["calls"] += 1
    return usage["calls"] <= DAILY_CAP


async def forward(req: web.Request) -> web.Response:
    name, tail = req.match_info["api"], req.match_info["tail"].lstrip("/")
    if name not in UPSTREAM:
        raise web.HTTPNotFound()
    if not authorized(req):
        return web.json_response({"error": "unauthorized"}, status=401)
    if not under_cap():
        return web.json_response({"error": "Shadow Cursor reached today's limit"}, status=429)
    url, env, header = UPSTREAM[name]
    key = os.environ[env]
    headers = {header: f"Bearer {key}" if header == "Authorization" else key,
               "Content-Type": req.headers.get("Content-Type", "application/json")}
    async with http.request(req.method, url + (f"/{tail}" if tail else ""), headers=headers,
                            data=await req.read()) as r:
        body = await r.read()
        return web.Response(status=r.status, body=body,
                            content_type=r.headers.get("Content-Type", "application/json").split(";")[0])


async def index(_req: web.Request) -> web.FileResponse:
    return web.FileResponse(HERE / "index.html", headers={"Cache-Control": "no-cache"})


async def dmg(_req: web.Request) -> web.FileResponse:
    return web.FileResponse(HERE / "Shadow-Cursor.dmg", headers={
        "Content-Disposition": 'attachment; filename="Shadow Cursor.dmg"'})


async def health(_req: web.Request) -> web.Response:
    return web.json_response({"ok": True, "calls_today": usage["calls"]})


async def startup(_app: web.Application) -> None:
    global http
    http = ClientSession(timeout=ClientTimeout(total=60))


def main() -> None:
    app = web.Application(client_max_size=25 * 1024 * 1024)  # screenshots
    app.on_startup.append(startup)
    app.add_routes([web.get("/", index), web.get("/Shadow-Cursor.dmg", dmg), web.get("/healthz", health),
                    web.route("*", "/api/{api}{tail:/?.*}", forward)])
    web.run_app(app, port=int(os.environ.get("PORT", "8080")))


if __name__ == "__main__":
    main()
