"""HTMX explorer dashboard (read-only)."""

from __future__ import annotations

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

RPC = "http://127.0.0.1:26657"
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
app = FastAPI(title="Clearmesh Explorer")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    async with httpx.AsyncClient() as client:
        status = (await client.get(f"{RPC}/v1/status")).json()
        try:
            latest = (await client.get(f"{RPC}/v1/blocks/latest")).json()
        except Exception:  # noqa: BLE001
            latest = None
        inv = (await client.get(f"{RPC}/v1/invariants")).json()
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "status": status, "latest": latest, "inv": inv},
    )


@app.get("/blocks", response_class=HTMLResponse)
async def blocks(request: Request) -> HTMLResponse:
    async with httpx.AsyncClient() as client:
        status = (await client.get(f"{RPC}/v1/status")).json()
        rows = []
        h = status["height"]
        for i in range(max(1, h - 19), h + 1):
            try:
                rows.append((await client.get(f"{RPC}/v1/blocks/{i}")).json())
            except Exception:  # noqa: BLE001
                pass
    return templates.TemplateResponse(
        "blocks.html", {"request": request, "blocks": list(reversed(rows))}
    )
