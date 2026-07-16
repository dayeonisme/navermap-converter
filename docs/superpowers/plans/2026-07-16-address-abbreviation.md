# Address Abbreviation Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract Korean addresses that begin with common abbreviated province/city names and give clear feedback when direct text input produces no addresses.

**Architecture:** Extend the parser's `_SIDO` alternation while preserving the matched source text, so the existing road-name and lot-number patterns continue to own address validation. Keep the API response contract unchanged; update the single-page UI to handle empty and failed `/parse-text` responses explicitly.

**Tech Stack:** Python 3.9, FastAPI 0.111, pytest 8.2, vanilla JavaScript

## Global Constraints

- Continue recognizing every full province/city name currently supported by the parser.
- Recognize common abbreviations: `서울`, `부산`, `대구`, `인천`, `광주`, `대전`, `울산`, `세종`, `경기`, `강원`, `충북`, `충남`, `전북`, `전남`, `경북`, `경남`, `제주`.
- Preserve the user's original province/city spelling in `raw_text` and `display_text`.
- Do not change road-name, lot-number, deduplication, or alias extraction behavior.
- Show `인식된 주소가 없습니다. 시·군·구와 번지를 포함해 입력해 주세요.` when direct text parsing returns zero addresses.

---

## File Map

- Modify `parser/text_parser.py`: accept full and abbreviated province/city names.
- Modify `static/index.html`: report empty results, HTTP failures, and network failures.
- Modify `tests/test_text_parser.py`: cover the reported three-line input and full-name compatibility.
- Modify `tests/test_api.py`: cover the reported input through `/parse-text` and assert the UI feedback code is served.

### Task 1: Parser and API support for abbreviated province/city names

**Files:**
- Modify: `parser/text_parser.py:5-11`
- Test: `tests/test_text_parser.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `extract_addresses(text: str, source_prefix: str) -> List[AddressItem]` and `POST /parse-text` with JSON `{ "text": str }`.
- Produces: the same interfaces, returning three `AddressItem` objects for the reported three-line input while preserving the abbreviated spelling.

- [ ] **Step 1: Add failing parser regression tests**

Append to `tests/test_text_parser.py`:

```python
def test_시도_축약형_지번주소_여러개_추출():
    text = (
        "서울 종로구 필운동 202\n"
        "서울 종로구 화동 138-21\n"
        "서울 마포구 상암동 33-4"
    )
    results = extract_addresses(text, source_prefix="직접입력")

    assert [item.display_text for item in results] == [
        "서울 종로구 필운동 202",
        "서울 종로구 화동 138-21",
        "서울 마포구 상암동 33-4",
    ]


@pytest.mark.parametrize(
    "address",
    [
        "서울특별시 강남구 역삼동 1-1",
        "서울 강남구 역삼동 1-1",
        "경기도 성남시 분당구 정자동 6-1",
        "경기 성남시 분당구 정자동 6-1",
        "제주특별자치도 제주시 연동 1-1",
        "제주 제주시 연동 1-1",
    ],
)
def test_시도_공식명칭과_축약형_모두_추출(address):
    results = extract_addresses(address, source_prefix="테스트")
    assert [item.display_text for item in results] == [address]
```

- [ ] **Step 2: Add a failing API regression test**

Append to `tests/test_api.py`:

```python
def test_parse_text_서울_축약형_지번주소_세개_반환():
    text = (
        "서울 종로구 필운동 202\n"
        "서울 종로구 화동 138-21\n"
        "서울 마포구 상암동 33-4"
    )
    response = client.post("/parse-text", json={"text": text})

    assert response.status_code == 200
    assert [item["display_text"] for item in response.json()["addresses"]] == text.splitlines()
```

- [ ] **Step 3: Run the focused tests and verify the reported input fails**

Run:

```bash
python3 -m pytest \
  tests/test_text_parser.py::test_시도_축약형_지번주소_여러개_추출 \
  tests/test_text_parser.py::test_시도_공식명칭과_축약형_모두_추출 \
  tests/test_api.py::test_parse_text_서울_축약형_지번주소_세개_반환 -v
```

Expected: the abbreviated cases fail because the returned lists are empty; existing full-name parameter cases pass.

- [ ] **Step 4: Extend `_SIDO` with explicit full-name and abbreviation alternatives**

Replace `_SIDO` in `parser/text_parser.py` with:

```python
_SIDO = (
    r"서울특별시|서울|부산광역시|부산|대구광역시|대구|인천광역시|인천"
    r"|광주광역시|광주|대전광역시|대전|울산광역시|울산|세종특별자치시|세종"
    r"|경기도|경기|강원특별자치도|강원도|강원|충청북도|충북|충청남도|충남"
    r"|전북특별자치도|전라북도|전북|전라남도|전남|경상북도|경북|경상남도|경남"
    r"|제주특별자치도|제주"
)
```

The longer alternatives remain before their prefixes. Because the match itself becomes `raw_text` and `display_text`, no normalization mapping is added.

- [ ] **Step 5: Run parser and API tests**

Run:

```bash
python3 -m pytest tests/test_text_parser.py tests/test_api.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit the parser/API change**

```bash
git add parser/text_parser.py tests/test_text_parser.py tests/test_api.py
git commit -m "fix: 시도 축약형 주소 인식"
```

### Task 2: Direct-input empty and error feedback

**Files:**
- Modify: `static/index.html:153-161`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `/parse-text` responses shaped as `{ "addresses": list }` or FastAPI error responses shaped as `{ "detail": value }`.
- Produces: the existing address list on success, an alert with the approved Korean message for zero results, and an alert for HTTP/network failures.

- [ ] **Step 1: Add a failing static-page contract test**

Append to `tests/test_api.py`:

```python
def test_index_직접입력_빈결과와_오류_안내_포함():
    response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert "인식된 주소가 없습니다. 시·군·구와 번지를 포함해 입력해 주세요." in html
    assert "if (!res.ok)" in html
    assert "catch (e)" in html
```

- [ ] **Step 2: Run the UI contract test and verify it fails**

Run:

```bash
python3 -m pytest tests/test_api.py::test_index_직접입력_빈결과와_오류_안내_포함 -v
```

Expected: FAIL because the empty-result guidance is absent and `parseText()` has no error handling.

- [ ] **Step 3: Add explicit empty-result and request-error handling**

Replace `parseText()` in `static/index.html` with:

```javascript
  async function parseText() {
    const text = document.getElementById('textInput').value.trim();
    if (!text) return;
    try {
      const res = await fetch('/parse-text', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({text})
      });
      if (!res.ok) {
        const error = await res.json();
        alert('주소 추출 실패: ' + (error.detail || `HTTP ${res.status}`));
        return;
      }
      const data = await res.json();
      if (!data.addresses.length) {
        alert('인식된 주소가 없습니다. 시·군·구와 번지를 포함해 입력해 주세요.');
        return;
      }
      setAddresses(data.addresses);
    } catch (e) {
      alert('오류: ' + e.message);
    }
  }
```

- [ ] **Step 4: Run the UI contract and full API tests**

Run:

```bash
python3 -m pytest tests/test_api.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit the UI feedback change**

```bash
git add static/index.html tests/test_api.py
git commit -m "fix: 주소 추출 빈 결과 안내"
```

### Task 3: Full regression and live behavior verification

**Files:**
- Verify only; no planned file changes.

**Interfaces:**
- Consumes: the completed parser, `/parse-text`, and browser UI.
- Produces: fresh evidence that the reported input works end to end and no existing test regressed.

- [ ] **Step 1: Run the complete automated test suite**

Run:

```bash
python3 -m pytest -v
```

Expected: all tests pass with zero failures.

- [ ] **Step 2: Verify the exact API payload**

Run against the restarted local server:

```bash
curl -sS http://127.0.0.1:8000/parse-text \
  -H 'Content-Type: application/json' \
  --data-binary '{"text":"서울 종로구 필운동 202\n서울 종로구 화동 138-21\n서울 마포구 상암동 33-4"}'
```

Expected: HTTP success JSON containing three address objects in input order.

- [ ] **Step 3: Verify the UI in the browser**

Open `http://localhost:8000`, paste the reported three lines, and click `주소 추출`.

Expected: the list shows `(3개)` and the three original abbreviated addresses. Entering `주소가 아닌 텍스트` instead shows the approved empty-result alert.

- [ ] **Step 4: Inspect the final diff and repository status**

Run:

```bash
git diff HEAD~2 --check
git status --short
```

Expected: no whitespace errors; only the user's pre-existing untracked screenshot files remain untracked.
