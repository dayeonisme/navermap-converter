# main.py
from __future__ import annotations
import asyncio
import json
import tempfile
from pathlib import Path
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from models import AddressItem
from naver.browser import NaverBrowser
from parser.excel_parser import parse_excel
from parser.pdf_parser import parse_pdf
from parser.text_parser import extract_addresses

app = FastAPI()

ALLOWED_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".csv"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# Singleton state
# _job_active: bool flag to prevent concurrent save jobs (using Lock.locked() has TOCTOU race)
_job_active: bool = False
_job_cancelled: bool = False
_browser: NaverBrowser | None = None
_progress_queue: asyncio.Queue | None = None
_item_registry: dict[str, AddressItem] = {}  # id -> AddressItem


def get_browser() -> NaverBrowser:
    global _browser
    if _browser is None:
        _browser = NaverBrowser()
    return _browser


# ── Parsing endpoints ─────────────────────────────────────────

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=422, detail=f"지원하지 않는 파일 형식: {suffix}")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=422, detail="파일 크기가 50MB를 초과합니다")

    # Windows-compatible temp file (avoids /tmp/ which doesn't exist on Windows)
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        f.write(content)
        tmp_path = Path(f.name)

    try:
        if suffix == ".pdf":
            items = parse_pdf(tmp_path)
        else:
            items = parse_excel(tmp_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파싱 오류: {e}")
    finally:
        tmp_path.unlink(missing_ok=True)

    _item_registry.clear()
    _item_registry.update({i.id: i for i in items})
    return {"addresses": [i.to_dict() for i in items]}


class ParseTextRequest(BaseModel):
    text: str


@app.post("/parse-text")
async def parse_text(req: ParseTextRequest):
    if len(req.text) > 1_000_000:  # 1MB text limit
        raise HTTPException(status_code=422, detail="텍스트가 너무 깁니다 (최대 1MB)")
    items = extract_addresses(req.text, source_prefix="붙여넣기")
    _item_registry.clear()
    _item_registry.update({i.id: i for i in items})
    return {"addresses": [i.to_dict() for i in items]}


@app.get("/login-status")
async def login_status():
    browser = get_browser()
    logged_in = await browser.is_logged_in()
    return {"logged_in": logged_in}


# ── Save endpoints ────────────────────────────────────────────

class SaveRequest(BaseModel):
    addresses: list[dict]


class RetryRequest(BaseModel):
    ids: list[str]


@app.post("/save", status_code=202)
async def save_addresses(req: SaveRequest):
    global _job_active, _job_cancelled, _progress_queue
    if _job_active:
        raise HTTPException(status_code=409, detail="이미 저장 작업이 진행 중입니다")
    _progress_queue = asyncio.Queue()
    _job_cancelled = False
    _job_active = True  # Set synchronously before create_task to prevent race
    asyncio.create_task(_run_save(req.addresses))
    return {"status": "accepted"}


@app.post("/cancel")
async def cancel_job():
    global _job_cancelled
    if not _job_active:
        raise HTTPException(status_code=404, detail="진행 중인 작업이 없습니다")
    _job_cancelled = True
    return {"status": "cancelling"}


class ResolveRequest(BaseModel):
    candidate_index: int


@app.post("/resolve/{item_id}")
async def resolve_ambiguous(item_id: str, req: ResolveRequest):
    global _job_active
    item = _item_registry.get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다")
    if item.status != "ambiguous":
        raise HTTPException(status_code=422, detail="ambiguous 상태의 항목만 선택할 수 있습니다")
    if _job_active:
        raise HTTPException(status_code=409, detail="이미 저장 작업이 진행 중입니다")

    _job_active = True
    try:
        from datetime import date
        from naver.map_saver import save_one_by_index

        browser = get_browser()
        page = await browser.get_page()
        list_name = f"AUTO_{date.today().strftime('%Y%m%d')}"
        status = await save_one_by_index(page, item.display_text, list_name, req.candidate_index)
        item.status = status
        return item.to_dict()
    finally:
        _job_active = False


@app.post("/retry", status_code=202)
async def retry_addresses(req: RetryRequest):
    global _job_active, _progress_queue
    if _job_active:
        raise HTTPException(status_code=409, detail="이미 저장 작업이 진행 중입니다")

    items = []
    rejected = []
    for id_ in req.ids:
        item = _item_registry.get(id_)
        if item is None or item.status != "failed":
            rejected.append(id_)
        else:
            items.append({"id": item.id, "display_text": item.display_text})

    if rejected:
        raise HTTPException(status_code=422, detail={"rejected_ids": rejected})

    _progress_queue = asyncio.Queue()
    _job_active = True
    asyncio.create_task(_run_save(items))
    return {"status": "accepted"}


@app.get("/progress")
async def progress():
    # Use _job_active single flag (avoids race between queue init and lock acquire)
    if not _job_active:
        return StreamingResponse(_empty_stream(), media_type="text/event-stream")
    return StreamingResponse(_stream_progress(), media_type="text/event-stream")


async def _empty_stream() -> AsyncGenerator[str, None]:
    yield ""


async def _stream_progress() -> AsyncGenerator[str, None]:
    global _progress_queue
    if _progress_queue is None:
        return
    while True:
        event = await _progress_queue.get()
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        if event.get("type") == "done":
            break


async def _run_save(address_dicts: list):
    global _job_active, _job_cancelled

    try:
        from datetime import date
        from naver.map_saver import save_addresses_to_naver

        browser = get_browser()

        # 로그인 확인: 저장된 쿠키 → Chrome 쿠키 → 수동 로그인 순서로 시도
        if not await browser.is_logged_in():
            await _progress_queue.put({"type": "trying_chrome_session"})
            imported = await browser.try_import_chrome_session()
            if not imported:
                await _progress_queue.put({"type": "waiting_for_login"})
                success = await browser.wait_for_login(timeout=120)
                if not success:
                    await _progress_queue.put({"type": "done", "error": "로그인 타임아웃"})
                    return

        list_name = f"AUTO_{date.today().strftime('%Y%m%d')}"
        try:
            await save_addresses_to_naver(
                browser=browser,
                list_name=list_name,
                addresses=address_dicts,
                item_registry=_item_registry,
                queue=_progress_queue,
                is_cancelled=lambda: _job_cancelled,
            )
        except Exception as e:
            await _progress_queue.put({"type": "done", "error": str(e)})
    finally:
        _job_active = False  # Always clear flag on completion or error


# ── Debug ─────────────────────────────────────────────────────

@app.get("/debug/frames")
async def debug_frames():
    """현재 페이지의 모든 frame URL 목록 반환."""
    browser = get_browser()
    page = await browser.get_page()
    frames = [{"url": f.url, "name": f.name} for f in page.frames]
    return {"frames": frames}


@app.get("/debug/links")
async def debug_links():
    """현재 페이지의 모든 a 태그 href + text 반환 (선택자 디버그용)."""
    browser = get_browser()
    page = await browser.get_page()
    links = await page.evaluate("""() => {
        return Array.from(document.querySelectorAll('a')).map(a => ({
            href: a.getAttribute('href') || '',
            text: a.innerText.trim().slice(0, 40),
            cls: a.className.slice(0, 60),
        }));
    }""")
    return {"url": page.url, "links": links}


@app.get("/debug/screenshot")
async def debug_screenshot():
    """브라우저 현재 화면을 sessions/debug_manual.png 로 저장 후 경로 반환."""
    from fastapi.responses import FileResponse
    from pathlib import Path
    browser = get_browser()
    page = await browser.get_page()
    path = Path(__file__).parent / "sessions" / "debug_manual.png"
    path.parent.mkdir(exist_ok=True)
    await page.screenshot(path=str(path), full_page=False)
    return FileResponse(str(path), media_type="image/png")


# ── Static files ──────────────────────────────────────────────

@app.get("/")
async def index():
    html_path = Path(__file__).parent / "static" / "index.html"
    if not html_path.exists():
        return HTMLResponse("<h1>UI not yet built</h1>")
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
