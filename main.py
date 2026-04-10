# main.py
from __future__ import annotations
import asyncio
import json
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, Optional

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from models import AddressItem
from naver.browser import NaverBrowser
from parser.excel_parser import parse_excel
from parser.pdf_parser import parse_pdf
from parser.text_parser import extract_addresses


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    if _browser is not None:
        try:
            await _browser.close()
        except Exception as e:
            import sys
            print(f"[lifespan] 브라우저 종료 중 오류: {e}", file=sys.stderr)


app = FastAPI(lifespan=lifespan)

ALLOWED_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".csv"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# Singleton state
# _job_active: bool flag to prevent concurrent save jobs (using Lock.locked() has TOCTOU race)
_job_active: bool = False
_job_cancelled: bool = False
_browser: Optional[NaverBrowser] = None
_progress_queue: asyncio.Queue | None = None
_item_registry: dict[str, AddressItem] = {}  # id -> AddressItem
_current_list_name: Optional[str] = None  # 진행 중/직전 작업의 리스트명 (retry에서 재사용)


def get_browser() -> NaverBrowser:
    global _browser
    if _browser is None:
        _browser = NaverBrowser()
    return _browser


# ── Parsing endpoints ─────────────────────────────────────────

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    if _job_active:
        raise HTTPException(status_code=409, detail="저장 작업이 진행 중입니다. 완료 후 업로드하세요")

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
    if _job_active:
        raise HTTPException(status_code=409, detail="저장 작업이 진행 중입니다. 완료 후 입력하세요")
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
    list_name: Optional[str] = None  # None이면 Auto_YYYYMMDD_HHMM 자동 생성


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
    asyncio.create_task(_run_save(req.addresses, req.list_name or None))
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
        from datetime import datetime
        from naver.map_saver import save_one_by_index

        browser = get_browser()
        page = await browser.get_page()
        list_name = _current_list_name or f"Auto_{datetime.now().strftime('%Y%m%d_%H%M')}"
        status = await save_one_by_index(page, item.display_text, list_name, req.candidate_index)
        item.status = status
        return item.to_dict()
    finally:
        _job_active = False


@app.post("/retry", status_code=202)
async def retry_addresses(req: RetryRequest):
    global _job_active, _job_cancelled, _progress_queue
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
    _job_cancelled = False
    _job_active = True
    asyncio.create_task(_run_save(items, _current_list_name))
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
        # Should not happen: _progress_queue is set before _job_active=True in /save and /retry
        yield f"data: {json.dumps({'type': 'done', 'error': '큐 초기화 오류'}, ensure_ascii=False)}\n\n"
        return
    while True:
        event = await _progress_queue.get()
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        if event.get("type") == "done":
            break


async def _run_save(address_dicts: list, list_name_override: Optional[str] = None):
    global _job_active, _job_cancelled, _current_list_name

    try:
        from datetime import datetime
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

        custom_name = list_name_override.strip() if list_name_override and list_name_override.strip() else None
        list_name = custom_name or f"Auto_{datetime.now().strftime('%Y%m%d_%H%M')}"
        _current_list_name = list_name
        _save_ok = False
        try:
            await save_addresses_to_naver(
                browser=browser,
                list_name=list_name,
                addresses=address_dicts,
                item_registry=_item_registry,
                queue=_progress_queue,
                is_cancelled=lambda: _job_cancelled,
                create_list=(custom_name is None),
            )
            _save_ok = True
        except RuntimeError as e:
            if "SESSION_EXPIRED" in str(e):
                # 쿠키는 있었지만 실제 세션 만료 → 재로그인 시도
                await browser._context.clear_cookies()
                await _progress_queue.put({"type": "trying_chrome_session"})
                imported = await browser.try_import_chrome_session()
                if not imported:
                    await _progress_queue.put({"type": "waiting_for_login"})
                    success = await browser.wait_for_login(timeout=120)
                    if not success:
                        await _progress_queue.put({"type": "done", "error": "로그인 타임아웃"})
                        return
                # 재로그인 성공 → 저장 재시도
                try:
                    await save_addresses_to_naver(
                        browser=browser,
                        list_name=list_name,
                        addresses=address_dicts,
                        item_registry=_item_registry,
                        queue=_progress_queue,
                        is_cancelled=lambda: _job_cancelled,
                        create_list=(custom_name is None),
                    )
                    _save_ok = True
                except Exception as e2:
                    await _progress_queue.put({"type": "done", "error": str(e2)})
            else:
                await _progress_queue.put({"type": "done", "error": str(e)})
        except Exception as e:
            await _progress_queue.put({"type": "done", "error": str(e)})
        if _save_ok:
            # done 이벤트 전송 후 headed 브라우저로 저장된 리스트 열기
            from naver.map_saver import _navigate_to_list
            await _navigate_to_list(list_name)
    finally:
        _job_active = False  # Always clear flag on completion or error

# ── Static files ──────────────────────────────────────────────

@app.get("/")
async def index():
    html_path = Path(__file__).parent / "static" / "index.html"
    if not html_path.exists():
        return HTMLResponse("<h1>UI not yet built</h1>")
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
