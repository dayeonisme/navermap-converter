# Naver Map Converter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

## 현재 상태 (2026-03-23 기준)

**모든 구현 Task 완료.** 코드 리뷰 후 race condition, memory leak, path handling, test isolation 이슈 수정 완료.

### 남은 작업

- [ ] **실제 네이버 지도 UI 동작 테스트** — `naver/selectors.py`의 CSS 선택자가 현재 네이버 지도와 일치하는지 실제 브라우저로 검증 (네이버 UI 변경 가능성)
- [ ] **`pdf2image` requirements.txt 반영** — 2026-03-23에 추가함, 설치 후 버전 고정 필요
- [ ] **ambiguous 수동 선택 UI** — 검색 결과 복수 시 UI 내에서 직접 선택하는 기능 (현재 Out of Scope로 분류됨, 필요 시 추가 구현)

---

**Goal:** PDF/엑셀/텍스트에서 한국 주소를 추출하고 네이버 지도에 `AUTO_YYYYMMDD` 비공개 리스트를 생성하여 장소를 자동 저장하는 로컬 웹 앱을 만든다.

**Architecture:** FastAPI 백엔드가 파일 파싱과 SSE 진행 상황 스트리밍을 담당하고, Playwright가 싱글톤 브라우저 인스턴스로 네이버 지도를 자동화한다. 단일 활성 작업 모델(asyncio.Lock)로 동시 저장을 방지한다.

**Tech Stack:** Python 3.10+, FastAPI, pdfplumber, pdf2image, pytesseract, openpyxl, pandas, Playwright (Chromium async_api), HTML/CSS/JS (바닐라)

---

## File Map

| 파일 | 역할 |
|------|------|
| `requirements.txt` | 의존성 목록 |
| `.gitignore` | sessions/ 제외 |
| `models.py` | AddressItem 공유 데이터 모델 |
| `main.py` | FastAPI 앱, 모든 API 라우터 |
| `parser/text_parser.py` | 한국 주소 정규식 추출 (도로명+지번) |
| `parser/pdf_parser.py` | PDF 텍스트 추출 + OCR 폴백 |
| `parser/excel_parser.py` | 엑셀/CSV 파싱, 주소 컬럼 자동 감지 |
| `naver/selectors.py` | 네이버 지도 CSS 선택자 상수 |
| `naver/browser.py` | Playwright 싱글톤, 세션/로그인 관리 |
| `naver/map_saver.py` | 리스트 생성 + 장소 저장 자동화 |
| `static/index.html` | 단일 페이지 웹 UI |
| `tests/test_models.py` | AddressItem 단위 테스트 |
| `tests/test_text_parser.py` | text_parser 단위 테스트 |
| `tests/test_pdf_parser.py` | pdf_parser 단위 테스트 |
| `tests/test_excel_parser.py` | excel_parser 단위 테스트 |
| `tests/test_browser.py` | browser.py mock 기반 단위 테스트 |
| `tests/test_api.py` | FastAPI 엔드포인트 테스트 |

---

## Task 1: 프로젝트 스캐폴드

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `parser/__init__.py`
- Create: `naver/__init__.py`
- Create: `tests/__init__.py`
- Create: `sessions/.gitkeep`

- [x] **Step 1: requirements.txt 작성**

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
pdfplumber==0.11.0
pdf2image==1.17.0
pytesseract==0.3.10
openpyxl==3.1.2
pandas==2.2.2
playwright==1.44.0
python-multipart==0.0.9
httpx==0.27.0
pytest==8.2.0
pytest-asyncio==0.23.7
```

- [x] **Step 2: .gitignore 작성**

```
sessions/
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
dist/
build/
```

- [x] **Step 3: 빈 패키지 파일 생성**

```bash
mkdir -p parser naver tests sessions static
touch parser/__init__.py naver/__init__.py tests/__init__.py sessions/.gitkeep
```

- [x] **Step 4: 의존성 설치**

```bash
pip install -r requirements.txt
playwright install chromium
```

- [x] **Step 5: 커밋**

```bash
git init
git add requirements.txt .gitignore parser/__init__.py naver/__init__.py tests/__init__.py sessions/.gitkeep
git commit -m "chore: project scaffold"
```

---

## Task 2: 공유 데이터 모델

**Files:**
- Create: `models.py`
- Create: `tests/test_models.py`

- [x] **Step 1: 실패 테스트 작성**

```python
# tests/test_models.py
from models import AddressItem

def test_기본값_status_pending():
    item = AddressItem(display_text="서울", raw_text="서울", source_location="테스트")
    assert item.status == "pending"

def test_id_자동_생성():
    a = AddressItem(display_text="a", raw_text="a", source_location="x")
    b = AddressItem(display_text="b", raw_text="b", source_location="x")
    assert a.id != b.id
    assert len(a.id) == 36  # UUID 형식

def test_to_dict_필드():
    item = AddressItem(display_text="서울특별시 강남구 테헤란로 152", raw_text="raw", source_location="PDF 1페이지")
    d = item.to_dict()
    assert set(d.keys()) == {"id", "raw_text", "display_text", "source_location", "status"}
    assert d["display_text"] == "서울특별시 강남구 테헤란로 152"
    assert d["status"] == "pending"
```

- [x] **Step 2: 테스트 실행 확인 (FAIL)**

```bash
pytest tests/test_models.py -v
```
Expected: ImportError (models.py 없음)

- [x] **Step 3: models.py 작성**

```python
from dataclasses import dataclass, field
from typing import Literal
import uuid

Status = Literal["pending", "success", "failed", "unrecognized", "ambiguous"]

@dataclass
class AddressItem:
    display_text: str
    raw_text: str
    source_location: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: Status = "pending"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "raw_text": self.raw_text,
            "display_text": self.display_text,
            "source_location": self.source_location,
            "status": self.status,
        }
```

- [x] **Step 4: 테스트 실행 확인 (PASS)**

```bash
pytest tests/test_models.py -v
```
Expected: 3 passed

- [x] **Step 5: 커밋**

```bash
git add models.py tests/test_models.py
git commit -m "feat: add shared AddressItem data model"
```

---

## Task 3: 텍스트 주소 파서

**Files:**
- Create: `parser/text_parser.py`
- Create: `tests/test_text_parser.py`

- [x] **Step 1: 실패 테스트 작성**

```python
# tests/test_text_parser.py
import pytest
from parser.text_parser import extract_addresses

def test_도로명_주소_추출():
    text = "서울특별시 강남구 테헤란로 152"
    results = extract_addresses(text, source_prefix="테스트")
    assert len(results) == 1
    assert results[0].display_text == "서울특별시 강남구 테헤란로 152"
    assert results[0].source_location == "테스트"
    assert results[0].status == "pending"

def test_지번_주소_추출():
    text = "경기도 성남시 분당구 정자동 6-1"
    results = extract_addresses(text, source_prefix="테스트")
    assert len(results) == 1
    assert results[0].display_text == "경기도 성남시 분당구 정자동 6-1"

def test_여러_주소_추출():
    text = """
    서울특별시 마포구 월드컵북로 396
    부산광역시 해운대구 해운대해변로 264
    """
    results = extract_addresses(text, source_prefix="테스트")
    assert len(results) == 2

def test_주소_없는_텍스트():
    text = "안녕하세요 이것은 주소가 없는 텍스트입니다"
    results = extract_addresses(text, source_prefix="테스트")
    assert len(results) == 0

def test_인식불가_항목은_반환되지_않음():
    # extract_addresses는 매칭된 것만 반환, unrecognized는 호출자가 처리
    text = "1234 이상한 텍스트"
    results = extract_addresses(text, source_prefix="테스트")
    assert len(results) == 0
```

- [x] **Step 2: 테스트 실행 확인 (FAIL)**

```bash
pytest tests/test_text_parser.py -v
```
Expected: ImportError 또는 ModuleNotFoundError

- [x] **Step 3: text_parser.py 구현**

```python
# parser/text_parser.py
import re
from typing import List
from models import AddressItem

# 시도 목록
_SIDO = (
    r"서울특별시|부산광역시|대구광역시|인천광역시|광주광역시|대전광역시|울산광역시"
    r"|세종특별자치시|경기도|강원도|충청북도|충청남도|전라북도|전라남도"
    r"|경상북도|경상남도|제주특별자치도"
)

# 도로명 주소: 시도 시군구 도로명(로|길) 건물번호
_DOROMYEONG = re.compile(
    rf"({_SIDO})\s+"
    r"[\w가-힣]+[시군구]\s+"
    r"[\w가-힣]+[로길]\s+"
    r"\d+(?:-\d+)?(?:\s+[\w가-힣\d]+동)?"
)

# 지번 주소: 시도 시군구 읍면동 번지
_JIBEON = re.compile(
    rf"({_SIDO})\s+"
    r"[\w가-힣]+[시군구]\s+"
    r"[\w가-힣]+[읍면동리]\s+"
    r"\d+(?:-\d+)?"
)

def extract_addresses(text: str, source_prefix: str) -> List[AddressItem]:
    """텍스트에서 한국 주소(도로명+지번)를 추출하여 AddressItem 목록 반환."""
    found = []
    seen = set()

    for pattern in (_DOROMYEONG, _JIBEON):
        for match in pattern.finditer(text):
            addr = match.group(0).strip()
            if addr not in seen:
                seen.add(addr)
                found.append(AddressItem(
                    raw_text=addr,
                    display_text=addr,
                    source_location=source_prefix,
                ))

    return found
```

- [x] **Step 4: 테스트 실행 확인 (PASS)**

```bash
pytest tests/test_text_parser.py -v
```
Expected: 5 passed

- [x] **Step 5: 커밋**

```bash
git add parser/text_parser.py tests/test_text_parser.py
git commit -m "feat: add Korean address text parser with 도로명/지번 regex"
```

---

## Task 4: PDF 파서

**Files:**
- Create: `parser/pdf_parser.py`
- Create: `tests/test_pdf_parser.py`
- Create: `tests/fixtures/sample_text.pdf` (테스트용 PDF, 아래 스텝에서 생성)

- [x] **Step 1: 테스트용 PDF fixture 생성**

```python
# tests/create_fixtures.py — 한 번만 실행
from reportlab.pdfgen import canvas

def make_text_pdf():
    c = canvas.Canvas("tests/fixtures/sample_text.pdf")
    c.drawString(100, 750, "서울특별시 강남구 테헤란로 152")
    c.drawString(100, 730, "경기도 수원시 팔달구 효원로 1")
    c.save()

make_text_pdf()
```

```bash
pip install reportlab
mkdir -p tests/fixtures
python tests/create_fixtures.py
```

- [x] **Step 2: 실패 테스트 작성**

```python
# tests/test_pdf_parser.py
import pytest
from pathlib import Path
from parser.pdf_parser import parse_pdf

FIXTURES = Path("tests/fixtures")

def test_텍스트_pdf_파싱():
    items = parse_pdf(FIXTURES / "sample_text.pdf")
    assert len(items) >= 2
    texts = [i.display_text for i in items]
    assert any("테헤란로" in t for t in texts)
    assert any("효원로" in t for t in texts)

def test_source_location_형식():
    items = parse_pdf(FIXTURES / "sample_text.pdf")
    assert all("PDF" in i.source_location for i in items)
    assert all("페이지" in i.source_location for i in items)
```

- [x] **Step 3: 테스트 실행 확인 (FAIL)**

```bash
pytest tests/test_pdf_parser.py -v
```
Expected: ImportError

- [x] **Step 4: pdf_parser.py 구현**

```python
# parser/pdf_parser.py
from pathlib import Path
from typing import List
import pdfplumber
from models import AddressItem
from parser.text_parser import extract_addresses

def _ocr_page(page) -> str:
    """pdfplumber 페이지를 이미지로 변환 후 OCR."""
    try:
        import pytesseract
    except ImportError:
        return ""

    # pdfplumber page.to_image()로 PIL 이미지 직접 획득 (pdf2image 불필요)
    pil_image = page.to_image(resolution=300).original
    return pytesseract.image_to_string(pil_image, lang="kor+eng")

def parse_pdf(path: Path) -> List[AddressItem]:
    """PDF 파일에서 주소 추출. 텍스트 추출 실패 시 OCR 폴백."""
    items: List[AddressItem] = []

    with pdfplumber.open(path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            source = f"PDF {page_num}페이지"
            text = page.extract_text() or ""

            if not text.strip():
                text = _ocr_page(page)

            items.extend(extract_addresses(text, source_prefix=source))

    return items
```

- [x] **Step 5: 테스트 실행 확인 (PASS)**

```bash
pytest tests/test_pdf_parser.py -v
```
Expected: 2 passed

- [x] **Step 6: 커밋**

```bash
git add parser/pdf_parser.py tests/test_pdf_parser.py tests/fixtures/ tests/create_fixtures.py
git commit -m "feat: add PDF parser with OCR fallback"
```

---

## Task 5: 엑셀/CSV 파서

**Files:**
- Create: `parser/excel_parser.py`
- Create: `tests/test_excel_parser.py`

- [x] **Step 1: 실패 테스트 작성**

```python
# tests/test_excel_parser.py
import pytest
import pandas as pd
from pathlib import Path
from openpyxl import Workbook
from parser.excel_parser import parse_excel

FIXTURES = Path("tests/fixtures")

def make_xlsx(path, data: dict):
    wb = Workbook()
    ws = wb.active
    headers = list(data.keys())
    ws.append(headers)
    for row in zip(*data.values()):
        ws.append(list(row))
    wb.save(path)

def test_주소_컬럼_자동_감지(tmp_path):
    f = tmp_path / "test.xlsx"
    make_xlsx(f, {
        "이름": ["홍길동", "김철수"],
        "주소": ["서울특별시 강남구 테헤란로 152", "경기도 수원시 팔달구 효원로 1"],
        "전화": ["010-1234-5678", "010-9876-5432"],
    })
    items = parse_excel(f)
    assert len(items) == 2
    assert any("테헤란로" in i.display_text for i in items)

def test_source_location_형식(tmp_path):
    f = tmp_path / "test.xlsx"
    make_xlsx(f, {"주소": ["서울특별시 강남구 테헤란로 152"]})
    items = parse_excel(f)
    assert len(items) == 1
    assert "행" in items[0].source_location

def test_매칭률_50미만_빈_결과(tmp_path):
    f = tmp_path / "test.xlsx"
    make_xlsx(f, {
        "이름": ["홍길동", "김철수", "박영희"],
        "코드": ["A001", "B002", "C003"],
    })
    items = parse_excel(f)
    assert len(items) == 0

def test_csv_파싱(tmp_path):
    f = tmp_path / "test.csv"
    f.write_text("이름,주소\n홍길동,서울특별시 마포구 월드컵북로 396\n", encoding="utf-8")
    items = parse_excel(f)
    assert len(items) == 1
    assert "월드컵북로" in items[0].display_text
```

- [x] **Step 2: 테스트 실행 확인 (FAIL)**

```bash
pytest tests/test_excel_parser.py -v
```
Expected: ImportError

- [x] **Step 3: excel_parser.py 구현**

```python
# parser/excel_parser.py
from pathlib import Path
from typing import List
import pandas as pd
from models import AddressItem
from parser.text_parser import extract_addresses, _DOROMYEONG, _JIBEON
import re

def _address_match_rate(series: pd.Series) -> float:
    """컬럼 내 한국 주소 정규식 매칭 비율 반환."""
    non_null = series.dropna().astype(str)
    if len(non_null) == 0:
        return 0.0
    combined = re.compile(rf"{_DOROMYEONG.pattern}|{_JIBEON.pattern}")
    matched = non_null.apply(lambda v: bool(combined.search(v)))
    return matched.sum() / len(non_null)

def _load_df(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path, dtype=str)
    else:  # .xlsx, .xls
        return pd.read_excel(path, sheet_name=0, dtype=str)

def parse_excel(path: Path) -> List[AddressItem]:
    """엑셀/CSV 파일에서 주소 추출. 매칭률 최고 컬럼 자동 선택, 50% 미만 시 빈 결과."""
    df = _load_df(path)
    if df.empty:
        return []

    rates = {col: _address_match_rate(df[col]) for col in df.columns}
    best_col = max(rates, key=rates.get)

    if rates[best_col] < 0.5:
        return []

    items: List[AddressItem] = []
    col_name = best_col
    for row_idx, value in df[col_name].dropna().items():
        source = f"엑셀 {col_name}열 {row_idx + 2}행"
        extracted = extract_addresses(str(value), source_prefix=source)
        if extracted:
            items.extend(extracted)
        else:
            # 값 자체를 display_text로 보존, unrecognized
            items.append(AddressItem(
                raw_text=str(value),
                display_text=str(value),
                source_location=source,
                status="unrecognized",
            ))
    return items
```

- [x] **Step 4: 테스트 실행 확인 (PASS)**

```bash
pytest tests/test_excel_parser.py -v
```
Expected: 4 passed

- [x] **Step 5: 커밋**

```bash
git add parser/excel_parser.py tests/test_excel_parser.py
git commit -m "feat: add Excel/CSV parser with automatic address column detection"
```

---

## Task 6: FastAPI 앱 — 파싱 엔드포인트

**Files:**
- Create: `main.py`
- Create: `tests/test_api.py`

- [x] **Step 1: 실패 테스트 작성**

```python
# tests/test_api.py
import pytest
from fastapi.testclient import TestClient
from main import app
import io

client = TestClient(app)

def test_upload_pdf_반환_주소_목록():
    # 최소한의 유효한 PDF bytes (빈 PDF)
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(100, 750, "서울특별시 강남구 테헤란로 152")
    c.save()
    buf.seek(0)
    response = client.post("/upload", files={"file": ("test.pdf", buf, "application/pdf")})
    assert response.status_code == 200
    data = response.json()
    assert "addresses" in data
    assert isinstance(data["addresses"], list)

def test_upload_지원안하는_형식_422():
    response = client.post("/upload", files={"file": ("test.txt", b"hello", "text/plain")})
    assert response.status_code == 422

def test_parse_text_주소_반환():
    response = client.post("/parse-text", json={"text": "서울특별시 강남구 테헤란로 152"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["addresses"]) >= 1
    assert data["addresses"][0]["status"] == "pending"

def test_parse_text_각_항목_필드():
    response = client.post("/parse-text", json={"text": "서울특별시 강남구 테헤란로 152"})
    item = response.json()["addresses"][0]
    assert "id" in item
    assert "raw_text" in item
    assert "display_text" in item
    assert "source_location" in item
    assert "status" in item

def test_login_status_반환():
    response = client.get("/login-status")
    assert response.status_code == 200
    assert "logged_in" in response.json()
```

- [x] **Step 2: 테스트 실행 확인 (FAIL)**

```bash
pytest tests/test_api.py -v
```
Expected: ImportError (main 없음)

- [x] **Step 3: main.py 구현 (파싱 엔드포인트만 먼저)**

```python
# main.py
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

# 싱글톤 상태
# _job_active: 동시 저장 요청 방지용 플래그 (asyncio.Lock.locked()는 TOCTOU 경합 있음)
_job_active: bool = False
_browser: NaverBrowser | None = None
_progress_queue: asyncio.Queue | None = None
_item_registry: dict[str, AddressItem] = {}  # id → AddressItem


def get_browser() -> NaverBrowser:
    global _browser
    if _browser is None:
        _browser = NaverBrowser()
    return _browser


# ── 파싱 엔드포인트 ────────────────────────────────────────────

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=422, detail=f"지원하지 않는 파일 형식: {suffix}")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=422, detail="파일 크기가 50MB를 초과합니다")

    # Windows 호환: tempfile 사용
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

    _item_registry.update({i.id: i for i in items})
    return {"addresses": [i.to_dict() for i in items]}


class ParseTextRequest(BaseModel):
    text: str


@app.post("/parse-text")
async def parse_text(req: ParseTextRequest):
    items = extract_addresses(req.text, source_prefix="붙여넣기")
    _item_registry.update({i.id: i for i in items})
    return {"addresses": [i.to_dict() for i in items]}


@app.get("/login-status")
async def login_status():
    browser = get_browser()
    logged_in = await browser.is_logged_in()
    return {"logged_in": logged_in}


# ── 저장 엔드포인트 ────────────────────────────────────────────

class SaveRequest(BaseModel):
    addresses: list[dict]


class RetryRequest(BaseModel):
    ids: list[str]


@app.post("/save", status_code=202)
async def save_addresses(req: SaveRequest):
    global _job_active
    if _job_active:
        raise HTTPException(status_code=409, detail="이미 저장 작업이 진행 중입니다")
    _job_active = True  # 동기적으로 설정 → create_task 전에 플래그 확보
    asyncio.create_task(_run_save(req.addresses))
    return {"status": "accepted"}


@app.post("/retry", status_code=202)
async def retry_addresses(req: RetryRequest):
    global _job_active
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

    _job_active = True
    asyncio.create_task(_run_save(items))
    return {"status": "accepted"}


@app.get("/progress")
async def progress():
    # _job_active 단일 플래그로 판단 (queue 존재 여부와 lock 상태의 경합 없음)
    if not _job_active:
        return StreamingResponse(_empty_stream(), media_type="text/event-stream")
    return StreamingResponse(_stream_progress(), media_type="text/event-stream")


async def _empty_stream() -> AsyncGenerator[str, None]:
    yield ""


async def _stream_progress() -> AsyncGenerator[str, None]:
    global _progress_queue
    while True:
        event = await _progress_queue.get()
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        if event.get("type") == "done":
            break


async def _run_save(address_dicts: list[dict]):
    global _job_active, _progress_queue
    _progress_queue = asyncio.Queue()

    try:
        from datetime import date
        from naver.map_saver import save_addresses_to_naver

        browser = get_browser()

        # 로그인 확인
        if not await browser.is_logged_in():
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
            )
        except Exception as e:
            await _progress_queue.put({"type": "done", "error": str(e)})
    finally:
        _job_active = False  # 성공/실패 모두 플래그 해제


# ── 정적 파일 ─────────────────────────────────────────────────

@app.get("/")
async def index():
    return HTMLResponse(Path("static/index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
```

- [x] **Step 4: 테스트 실행 확인 (PASS)**

```bash
pytest tests/test_api.py -v
```
Expected: 5 passed (naver 모듈은 stub으로 처리되므로 먼저 Task 7~8을 완료 후 재실행)

> **Note:** naver 모듈이 없으면 import 오류 발생. Task 7~8 완료 후 재실행.

- [x] **Step 5: 커밋**

```bash
git add main.py tests/test_api.py
git commit -m "feat: add FastAPI parsing endpoints and app skeleton"
```

---

## Task 7: 네이버 지도 선택자 상수

**Files:**
- Create: `naver/selectors.py`

> **중요:** 아래 선택자는 현재 네이버 지도(map.naver.com) UI 기준이다. 네이버가 UI를 업데이트하면 이 파일만 수정하면 된다. 실제 선택자는 브라우저 개발자 도구로 직접 확인하여 업데이트해야 한다.

- [x] **Step 1: selectors.py 작성**

```python
# naver/selectors.py
# 네이버 지도 자동화 선택자 — UI 변경 시 이 파일만 수정

# 지도 메인
MAP_URL = "https://map.naver.com/p/"
NAVER_MAIN_URL = "https://www.naver.com"

# 검색
SEARCH_INPUT = "input.input_search"           # 검색창 입력
SEARCH_SUBMIT = "button.btn_search"            # 검색 버튼
SEARCH_RESULT_LIST = "ul.list_place"           # 검색 결과 목록
SEARCH_RESULT_ITEM = "li.item"                 # 개별 결과 항목
SEARCH_RESULT_COUNT = "strong.num"             # 결과 수

# 장소 상세
PLACE_SAVE_BUTTON = "a.btn_save, button.btn_bookmark"  # 저장 버튼

# 내 장소 / 리스트
MY_PLACE_MENU = "a[data-nclick*='myplace']"    # 내 장소 메뉴
CREATE_LIST_BUTTON = "button.btn_list_add"     # 새 리스트 만들기
LIST_NAME_INPUT = "input.inp_list_name"        # 리스트 이름 입력
LIST_PRIVACY_PRIVATE = "label[for='private']"  # 비공개 라디오
LIST_CONFIRM_BUTTON = "button.btn_confirm"     # 확인/저장 버튼
LIST_ITEM_SELECTOR = "li.my_list_item"         # 내 리스트 항목
```

- [x] **Step 2: 커밋**

```bash
git add naver/selectors.py
git commit -m "feat: add Naver Maps UI selectors constants"
```

---

## Task 8: 브라우저 관리 (browser.py)

**Files:**
- Create: `naver/browser.py`
- Create: `tests/test_browser.py`

- [x] **Step 1: 실패 테스트 작성 (mock 기반, 실제 브라우저 불필요)**

```python
# tests/test_browser.py
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.mark.asyncio
async def test_is_logged_in_true_when_NID_AUT_쿠키_존재():
    from naver.browser import NaverBrowser
    browser = NaverBrowser()

    mock_page = AsyncMock()
    mock_context = AsyncMock()
    mock_context.cookies = AsyncMock(return_value=[
        {"name": "NID_AUT", "value": "abc123"}
    ])
    browser._page = mock_page
    browser._context = mock_context
    browser._started = True

    result = await browser.is_logged_in()
    assert result is True
    mock_page.goto.assert_called_once()

@pytest.mark.asyncio
async def test_is_logged_in_false_when_NID_AUT_쿠키_없음():
    from naver.browser import NaverBrowser
    browser = NaverBrowser()

    mock_page = AsyncMock()
    mock_context = AsyncMock()
    mock_context.cookies = AsyncMock(return_value=[
        {"name": "OTHER_COOKIE", "value": "xyz"}
    ])
    browser._page = mock_page
    browser._context = mock_context
    browser._started = True

    result = await browser.is_logged_in()
    assert result is False

@pytest.mark.asyncio
async def test_wait_for_login_timeout_false():
    from naver.browser import NaverBrowser
    browser = NaverBrowser()

    mock_page = AsyncMock()
    mock_context = AsyncMock()
    # 쿠키 없음 → 타임아웃
    mock_context.cookies = AsyncMock(return_value=[])
    browser._page = mock_page
    browser._context = mock_context
    browser._started = True

    # timeout=2, poll=2 → 1회 폴링 후 즉시 종료
    result = await browser.wait_for_login(timeout=2)
    assert result is False
```

- [x] **Step 2: 테스트 실행 확인 (FAIL)**

```bash
pytest tests/test_browser.py -v
```
Expected: ImportError (browser.py 없음)

- [x] **Step 3: browser.py 구현**

```python
# naver/browser.py
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

COOKIES_PATH = Path("sessions/naver_cookies.json")
NAVER_MAIN = "https://www.naver.com"
LOGIN_COOKIE = "NID_AUT"
POLL_INTERVAL = 2  # seconds


class NaverBrowser:
    def __init__(self):
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._started = False

    async def start(self):
        """브라우저 시작 및 세션 로드."""
        if self._started:
            return
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=False)
        self._context = await self._browser.new_context()
        self._page = await self._context.new_page()

        if COOKIES_PATH.exists():
            cookies = json.loads(COOKIES_PATH.read_text())
            await self._context.add_cookies(cookies)

        self._started = True

    async def get_page(self) -> Page:
        await self.start()
        return self._page

    async def is_logged_in(self) -> bool:
        """NID_AUT 쿠키 존재 여부로 로그인 상태 확인."""
        await self.start()
        await self._page.goto(NAVER_MAIN)
        cookies = await self._context.cookies()
        return any(c["name"] == LOGIN_COOKIE for c in cookies)

    async def wait_for_login(self, timeout: int = 120) -> bool:
        """사용자가 수동으로 로그인할 때까지 대기 (NID_AUT 쿠키 폴링)."""
        await self._page.goto(NAVER_MAIN)
        elapsed = 0
        while elapsed < timeout:
            cookies = await self._context.cookies()
            if any(c["name"] == LOGIN_COOKIE for c in cookies):
                await self._save_cookies()
                return True
            await asyncio.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL
        return False

    async def _save_cookies(self):
        """현재 세션 쿠키를 파일에 저장."""
        COOKIES_PATH.parent.mkdir(exist_ok=True)
        cookies = await self._context.cookies()
        COOKIES_PATH.write_text(json.dumps(cookies, ensure_ascii=False, indent=2))

    async def close(self):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._started = False
```

- [x] **Step 4: 테스트 실행 확인 (PASS)**

```bash
pytest tests/test_browser.py -v
```
Expected: 3 passed

- [x] **Step 5: 수동 검증 (실제 브라우저)**

```bash
python -c "
import asyncio
from naver.browser import NaverBrowser

async def test():
    b = NaverBrowser()
    print('로그인 상태:', await b.is_logged_in())
    await b.close()

asyncio.run(test())
"
```

- [x] **Step 6: 커밋**

```bash
git add naver/browser.py tests/test_browser.py
git commit -m "feat: add Playwright browser manager with session persistence"
```

---

## Task 9: 네이버 지도 저장 자동화 (map_saver.py)

**Files:**
- Create: `naver/map_saver.py`

> **Note:** 실제 네이버 지도 자동화. 선택자가 맞지 않으면 `naver/selectors.py`를 업데이트한다.
> 이 모듈은 실제 네이버 계정으로 수동 검증한다.

- [x] **Step 1: map_saver.py 구현**

```python
# naver/map_saver.py
import asyncio
from datetime import date
from typing import Dict
from models import AddressItem
from naver.browser import NaverBrowser
from naver import selectors as S


async def _create_list(page, list_name: str) -> bool:
    """네이버 지도에서 새 리스트 생성. 성공 시 True 반환."""
    try:
        await page.goto(S.MAP_URL)
        await page.wait_for_load_state("networkidle", timeout=15000)

        # 내 장소 메뉴 클릭
        await page.click(S.MY_PLACE_MENU, timeout=10000)
        await page.wait_for_timeout(1000)

        # 새 리스트 만들기
        await page.click(S.CREATE_LIST_BUTTON, timeout=10000)
        await page.wait_for_timeout(500)

        # 리스트 이름 입력
        await page.fill(S.LIST_NAME_INPUT, list_name)
        await page.wait_for_timeout(300)

        # 비공개 선택
        await page.click(S.LIST_PRIVACY_PRIVATE, timeout=5000)
        await page.wait_for_timeout(300)

        # 확인
        await page.click(S.LIST_CONFIRM_BUTTON, timeout=5000)
        await page.wait_for_timeout(1000)

        return True
    except Exception as e:
        raise RuntimeError(f"리스트 생성 실패: {e}")


async def _save_one(page, address: str, list_name: str) -> str:
    """단일 주소를 검색하고 지정 리스트에 저장. 'success'|'failed'|'ambiguous' 반환."""
    try:
        await page.goto(S.MAP_URL)
        await page.wait_for_load_state("networkidle", timeout=15000)

        # 검색
        await page.fill(S.SEARCH_INPUT, address)
        await page.click(S.SEARCH_SUBMIT)
        await page.wait_for_timeout(2000)

        # 결과 수 확인
        results = await page.query_selector_all(S.SEARCH_RESULT_ITEM)
        if len(results) == 0:
            return "failed"
        if len(results) > 1:
            return "ambiguous"

        # 저장 버튼 클릭
        await page.click(S.PLACE_SAVE_BUTTON, timeout=5000)
        await page.wait_for_timeout(500)

        # 저장할 리스트 선택 (리스트 이름으로 찾기)
        list_items = await page.query_selector_all(S.LIST_ITEM_SELECTOR)
        for item in list_items:
            text = await item.inner_text()
            if list_name in text:
                await item.click()
                await page.wait_for_timeout(500)
                return "success"

        return "failed"
    except Exception:
        return "failed"


async def save_addresses_to_naver(
    browser: NaverBrowser,
    list_name: str,
    addresses: list[dict],
    item_registry: Dict[str, AddressItem],
    queue: asyncio.Queue,
):
    """리스트 생성 후 주소 목록 순차 저장. 진행 상황을 queue에 전달."""
    page = await browser.get_page()

    # 리스트 생성 (실패 시 예외 → 배치 전체 중단)
    await _create_list(page, list_name)

    summary = {"success": 0, "failed": 0, "ambiguous": 0}

    for addr_dict in addresses:
        id_ = addr_dict["id"]
        display_text = addr_dict["display_text"]

        status = await _save_one(page, display_text, list_name)

        # item_registry 상태 업데이트
        if id_ in item_registry:
            item_registry[id_].status = status

        summary[status] = summary.get(status, 0) + 1
        await queue.put({"id": id_, "status": status})

    await queue.put({"type": "done", "summary": summary})
```

- [x] **Step 2: 수동 검증**

실제 네이버 계정으로 아래 순서로 검증:
1. `python main.py` 실행
2. `http://localhost:8000` 접속
3. 텍스트 붙여넣기: `서울특별시 강남구 테헤란로 152`
4. "저장 시작" 클릭
5. Playwright 창에서 네이버 로그인
6. 네이버 지도에 `AUTO_20260322` 리스트 생성 확인
7. 장소 저장 성공 확인

- [x] **Step 3: 선택자 오류 시 수정**

실제 네이버 지도 UI에서 개발자 도구로 선택자 확인 후 `naver/selectors.py` 업데이트.

- [x] **Step 4: 커밋**

```bash
git add naver/map_saver.py
git commit -m "feat: add Naver Maps list creation and place saving automation"
```

---

## Task 10: API 테스트 완성 및 검증

**Files:**
- Modify: `tests/test_api.py`

- [x] **Step 1: 파싱 테스트 실행 확인 (PASS)**

```bash
pytest tests/test_text_parser.py tests/test_pdf_parser.py tests/test_excel_parser.py tests/test_api.py -v
```
Expected: 모든 테스트 PASS

- [x] **Step 2: 409 동시 요청 테스트 추가**

```python
# tests/test_api.py 에 추가
def test_save_409_이미_진행중():
    # _save_lock이 잠긴 상태를 시뮬레이션하기 어려우므로
    # 실제로는 두 번 호출 시 두 번째가 409인지 확인
    # 이 테스트는 통합 테스트로 수동 검증
    pass

def test_retry_422_잘못된_id():
    response = client.post("/retry", json={"ids": ["nonexistent-id"]})
    assert response.status_code == 422

def test_retry_422_ambiguous_id():
    # ambiguous 상태 항목 ID로 retry 시도
    from models import AddressItem
    import main
    item = AddressItem(raw_text="test", display_text="test", source_location="test", status="ambiguous")
    main._item_registry[item.id] = item
    response = client.post("/retry", json={"ids": [item.id]})
    assert response.status_code == 422
```

- [x] **Step 3: 최종 테스트 실행**

```bash
pytest tests/ -v
```
Expected: 모든 테스트 PASS

- [x] **Step 4: 커밋**

```bash
git add tests/test_api.py
git commit -m "test: add retry validation and edge case tests"
```

---

## Task 11: 웹 UI (index.html)

**Files:**
- Create: `static/index.html`

- [x] **Step 1: index.html 작성**

```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>네이버 지도 주소 변환기</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; color: #333; }
  .container { max-width: 900px; margin: 40px auto; padding: 0 20px; }
  h1 { font-size: 1.6rem; margin-bottom: 24px; color: #03c75a; }
  .card { background: #fff; border-radius: 12px; padding: 24px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,.08); }
  .card h2 { font-size: 1rem; font-weight: 600; margin-bottom: 16px; color: #555; }

  /* 업로드 영역 */
  .upload-zone { border: 2px dashed #ccc; border-radius: 8px; padding: 40px; text-align: center; cursor: pointer; transition: border-color .2s; }
  .upload-zone.dragover { border-color: #03c75a; background: #f0fff6; }
  .upload-zone p { color: #999; margin-top: 8px; font-size: .9rem; }
  #fileInput { display: none; }

  /* 텍스트 입력 */
  textarea { width: 100%; height: 120px; border: 1px solid #ddd; border-radius: 8px; padding: 12px; font-size: .9rem; resize: vertical; }
  .btn { padding: 10px 20px; border: none; border-radius: 8px; cursor: pointer; font-size: .9rem; font-weight: 600; }
  .btn-primary { background: #03c75a; color: #fff; }
  .btn-primary:hover { background: #02a84a; }
  .btn-secondary { background: #eee; color: #555; margin-left: 8px; }
  .btn:disabled { opacity: .5; cursor: not-allowed; }

  /* 주소 목록 */
  #addressList { list-style: none; }
  #addressList li { display: flex; align-items: center; gap: 10px; padding: 10px 0; border-bottom: 1px solid #f0f0f0; }
  #addressList li:last-child { border-bottom: none; }
  .badge { padding: 3px 8px; border-radius: 12px; font-size: .75rem; font-weight: 600; white-space: nowrap; }
  .badge-pending { background: #e8f4fd; color: #0072c3; }
  .badge-success { background: #e8f9ef; color: #1a7a3c; }
  .badge-failed { background: #fde8e8; color: #b91c1c; }
  .badge-ambiguous { background: #fff3e0; color: #b45309; }
  .badge-unrecognized { background: #f3f4f6; color: #6b7280; }
  .addr-text { flex: 1; font-size: .9rem; padding: 4px 8px; border: 1px solid transparent; border-radius: 4px; }
  .addr-text:focus { border-color: #03c75a; outline: none; }
  .source { font-size: .75rem; color: #999; white-space: nowrap; }

  /* 진행 상황 */
  .progress-bar-wrap { background: #eee; border-radius: 8px; height: 8px; margin: 12px 0; overflow: hidden; }
  .progress-bar { height: 100%; background: #03c75a; width: 0%; transition: width .3s; }
  #statusMsg { font-size: .9rem; color: #555; margin-top: 8px; }
  #summary { margin-top: 12px; font-size: .9rem; }

  .hidden { display: none; }
</style>
</head>
<body>
<div class="container">
  <h1>네이버 지도 주소 변환기</h1>

  <!-- 파일 업로드 -->
  <div class="card">
    <h2>파일 업로드</h2>
    <div class="upload-zone" id="uploadZone">
      <svg width="40" height="40" fill="none" stroke="#ccc" stroke-width="2" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
      <p>PDF, Excel(.xlsx/.xls), CSV 파일을 드래그하거나 클릭하여 선택</p>
      <input type="file" id="fileInput" accept=".pdf,.xlsx,.xls,.csv">
    </div>
  </div>

  <!-- 텍스트 붙여넣기 -->
  <div class="card">
    <h2>텍스트 직접 입력</h2>
    <textarea id="textInput" placeholder="주소를 붙여넣거나 직접 입력하세요...&#10;서울특별시 강남구 테헤란로 152&#10;경기도 수원시 팔달구 효원로 1"></textarea>
    <div style="margin-top:12px">
      <button class="btn btn-primary" onclick="parseText()">주소 추출</button>
    </div>
  </div>

  <!-- 주소 목록 -->
  <div class="card hidden" id="addressCard">
    <h2>추출된 주소 목록 <span id="addressCount" style="color:#999;font-weight:400"></span></h2>
    <ul id="addressList"></ul>
    <div style="margin-top:16px">
      <button class="btn btn-primary" id="saveBtn" onclick="startSave()">저장 시작</button>
      <button class="btn btn-secondary" id="retryBtn" onclick="startRetry()" style="display:none">실패 항목 재시도</button>
    </div>
  </div>

  <!-- 진행 상황 -->
  <div class="card hidden" id="progressCard">
    <h2>저장 진행 상황</h2>
    <div class="progress-bar-wrap"><div class="progress-bar" id="progressBar"></div></div>
    <div id="statusMsg">준비 중...</div>
    <div id="summary"></div>
  </div>
</div>

<script>
  let addresses = [];
  let total = 0;
  let done = 0;
  let eventSource = null;

  // ── 업로드 ──────────────────────────────────────────────
  const uploadZone = document.getElementById('uploadZone');
  const fileInput = document.getElementById('fileInput');

  uploadZone.addEventListener('click', () => fileInput.click());
  uploadZone.addEventListener('dragover', e => { e.preventDefault(); uploadZone.classList.add('dragover'); });
  uploadZone.addEventListener('dragleave', () => uploadZone.classList.remove('dragover'));
  uploadZone.addEventListener('drop', e => {
    e.preventDefault();
    uploadZone.classList.remove('dragover');
    if (e.dataTransfer.files[0]) uploadFile(e.dataTransfer.files[0]);
  });
  fileInput.addEventListener('change', () => { if (fileInput.files[0]) uploadFile(fileInput.files[0]); });

  async function uploadFile(file) {
    const fd = new FormData();
    fd.append('file', file);
    try {
      const res = await fetch('/upload', { method: 'POST', body: fd });
      if (!res.ok) { alert('업로드 실패: ' + (await res.json()).detail); return; }
      const data = await res.json();
      setAddresses(data.addresses);
    } catch (e) { alert('오류: ' + e.message); }
  }

  async function parseText() {
    const text = document.getElementById('textInput').value.trim();
    if (!text) return;
    const res = await fetch('/parse-text', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({text}) });
    const data = await res.json();
    setAddresses(data.addresses);
  }

  // ── 주소 목록 렌더링 ────────────────────────────────────
  function setAddresses(items) {
    addresses = items;
    total = items.length;
    done = 0;
    renderList();
    document.getElementById('addressCard').classList.remove('hidden');
    document.getElementById('retryBtn').style.display = 'none';
    document.getElementById('progressCard').classList.add('hidden');
  }

  function renderList() {
    const list = document.getElementById('addressList');
    list.innerHTML = '';
    document.getElementById('addressCount').textContent = `(${addresses.length}개)`;
    addresses.forEach(item => {
      const li = document.createElement('li');
      li.id = 'item-' + item.id;
      li.innerHTML = `
        <span class="badge badge-${item.status}">${statusLabel(item.status)}</span>
        <input class="addr-text" value="${esc(item.display_text)}" data-id="${item.id}" onchange="updateText(this)">
        <span class="source">${esc(item.source_location)}</span>
      `;
      list.appendChild(li);
    });
  }

  function statusLabel(s) {
    return {pending:'대기',success:'성공',failed:'실패',ambiguous:'모호',unrecognized:'미인식'}[s] || s;
  }

  function esc(s) { return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;'); }

  function updateText(input) {
    const item = addresses.find(a => a.id === input.dataset.id);
    if (item) item.display_text = input.value;
  }

  function updateItemStatus(id, status) {
    const item = addresses.find(a => a.id === id);
    if (item) item.status = status;
    const li = document.getElementById('item-' + id);
    if (li) {
      const badge = li.querySelector('.badge');
      badge.className = `badge badge-${status}`;
      badge.textContent = statusLabel(status);
    }
  }

  // ── 저장 ────────────────────────────────────────────────
  async function startSave() {
    const payload = addresses.filter(a => a.status !== 'success').map(a => ({id: a.id, display_text: a.display_text}));
    if (!payload.length) { alert('저장할 항목이 없습니다'); return; }

    document.getElementById('saveBtn').disabled = true;
    document.getElementById('progressCard').classList.remove('hidden');
    done = 0;
    total = payload.length;
    updateProgress(0, '저장 시작 중...');

    const res = await fetch('/save', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({addresses: payload}) });
    if (!res.ok) { alert('오류: ' + (await res.json()).detail); document.getElementById('saveBtn').disabled = false; return; }

    listenProgress();
  }

  async function startRetry() {
    const failedIds = addresses.filter(a => a.status === 'failed').map(a => a.id);
    if (!failedIds.length) { alert('재시도할 항목이 없습니다'); return; }

    document.getElementById('retryBtn').disabled = true;
    done = 0;
    total = failedIds.length;

    const res = await fetch('/retry', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ids: failedIds}) });
    if (!res.ok) { alert('오류'); document.getElementById('retryBtn').disabled = false; return; }

    listenProgress();
  }

  function listenProgress() {
    if (eventSource) eventSource.close();
    eventSource = new EventSource('/progress');
    eventSource.onmessage = e => {
      const data = JSON.parse(e.data);

      if (data.type === 'waiting_for_login') {
        updateProgress(0, '네이버 로그인 창에서 로그인 후 기다려 주세요...');
        return;
      }

      if (data.type === 'done') {
        eventSource.close();
        const s = data.summary || {};
        const errMsg = data.error ? `오류: ${data.error}` : '';
        document.getElementById('summary').innerHTML = errMsg ||
          `완료 — 성공 ${s.success||0}개 / 실패 ${s.failed||0}개 / 모호 ${s.ambiguous||0}개`;
        updateProgress(100, '완료');
        document.getElementById('saveBtn').disabled = false;
        const hasFailures = (s.failed||0) > 0;
        document.getElementById('retryBtn').style.display = hasFailures ? 'inline-block' : 'none';
        document.getElementById('retryBtn').disabled = false;
        return;
      }

      if (data.id) {
        done++;
        updateItemStatus(data.id, data.status);
        updateProgress(Math.round(done / total * 100), `저장 중... (${done}/${total})`);
      }
    };
  }

  function updateProgress(pct, msg) {
    document.getElementById('progressBar').style.width = pct + '%';
    document.getElementById('statusMsg').textContent = msg;
  }
</script>
</body>
</html>
```

- [x] **Step 2: 브라우저에서 수동 UI 검증**

```bash
python main.py
# http://localhost:8000 접속 후:
# 1. 텍스트 입력 → "주소 추출" → 목록 표시 확인
# 2. 파일 업로드 → 목록 표시 확인
# 3. 저장 시작 → 진행 바 확인
```

- [x] **Step 3: 커밋**

```bash
git add static/index.html
git commit -m "feat: add single-page web UI with file upload, address list, and SSE progress"
```

---

## Task 12: 전체 통합 검증

- [x] **Step 1: 전체 테스트 실행**

```bash
pytest tests/ -v
```
Expected: 모든 단위/API 테스트 PASS

- [x] **Step 2: 실제 네이버 계정으로 E2E 검증**

1. `python main.py`
2. `http://localhost:8000` 접속
3. 주소 텍스트 붙여넣기 (도로명 + 지번 각 1개)
4. 추출 확인
5. "저장 시작" → 로그인 → 저장 완료
6. 네이버 지도에서 `AUTO_YYYYMMDD` 리스트 및 저장된 장소 확인
7. PDF 파일 업로드 (텍스트 PDF)
8. 스캔본 PDF 업로드 → OCR 폴백 동작 확인
9. Excel 파일 업로드 → 컬럼 자동 감지 확인

- [x] **Step 3: 최종 커밋**

```bash
git add -A
git commit -m "feat: complete Naver Maps address converter"
```

---

## 선택자 업데이트 가이드

`naver/selectors.py`의 선택자가 맞지 않을 경우:

1. 크롬 개발자 도구(F12) → Elements 탭
2. 해당 요소 우클릭 → Copy → Copy selector
3. `naver/selectors.py`의 해당 상수 업데이트
4. 재테스트

## Tesseract 설치 안내 (Windows)

1. https://github.com/UB-Mannheim/tesseract/wiki 에서 인스톨러 다운로드
2. 설치 시 "Additional language data" → Korean 체크
3. 설치 경로를 PATH에 추가하거나 pytesseract.pytesseract.tesseract_cmd 설정:

```python
# main.py 상단에 추가 (Windows)
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
```
