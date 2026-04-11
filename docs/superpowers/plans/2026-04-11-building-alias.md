# Building Name Alias Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PDF에서 주소 앞 건물명을 자동 추출해 네이버 지도 저장 시 별명으로 등록하고, 웹 UI에서 사용자가 확인·수정할 수 있게 한다.

**Architecture:** 파서가 주소 매칭 위치 기준으로 같은 줄 앞 텍스트 → 바로 윗 줄 순서로 건물명 후보를 탐색해 `AddressItem.alias`에 저장한다. 저장 시 alias가 있으면 '+ 메모,별명,URL 추가' 버튼 클릭 후 별명 입력란에 기입한다. 별명 입력 실패는 저장 자체를 막지 않고 경고만 남긴다.

**Tech Stack:** Python 3.9, FastAPI, Playwright, vanilla JS

---

## File Map

| 파일 | 변경 |
|------|------|
| `models.py` | `alias: str = ""` 필드 추가 |
| `parser/text_parser.py` | `_find_alias()`, `_is_valid_alias()` 추가; `extract_addresses`에서 alias 세팅 |
| `naver/selectors.py` | `PLACE_SAVE_MEMO_BTN`, `PLACE_SAVE_ALIAS_INPUT` 추가 |
| `naver/map_saver.py` | `_save_in_entry_frame`, `_save_address_page`, `_save_one`, `save_addresses_to_naver`에 `alias` 파라미터 추가 |
| `static/index.html` | 주소 목록 행에 alias 인라인 input 추가; 저장 페이로드에 포함 |
| `tests/test_text_parser.py` | alias 추출 테스트 추가 |
| `tests/test_map_saver.py` | alias 전달 테스트 추가 |

---

### Task 1: `models.py` — alias 필드 추가

**Files:**
- Modify: `models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_models.py` 끝에 추가:
```python
def test_alias_기본값_빈문자열():
    item = AddressItem(raw_text="t", display_text="t", source_location="t")
    assert item.alias == ""

def test_alias_to_dict_포함():
    item = AddressItem(raw_text="t", display_text="t", source_location="t", alias="판교타워")
    d = item.to_dict()
    assert d["alias"] == "판교타워"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
python3 -m pytest tests/test_models.py::test_alias_기본값_빈문자열 tests/test_models.py::test_alias_to_dict_포함 -v
```
Expected: FAIL (AttributeError: alias)

- [ ] **Step 3: 구현**

`models.py`를 다음으로 교체:
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
    candidates: list = field(default_factory=list)
    alias: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "raw_text": self.raw_text,
            "display_text": self.display_text,
            "source_location": self.source_location,
            "status": self.status,
            "candidates": self.candidates,
            "alias": self.alias,
        }
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
python3 -m pytest tests/test_models.py -v
```
Expected: 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add models.py tests/test_models.py
git commit -m "feat: AddressItem에 alias 필드 추가"
```

---

### Task 2: `text_parser.py` — 건물명 추출 로직

**Files:**
- Modify: `parser/text_parser.py`
- Test: `tests/test_text_parser.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_text_parser.py` 끝에 추가:
```python
def test_같은줄_앞_건물명_추출():
    text = "판교타워 경기도 성남시 분당구 서현로 192"
    items = extract_addresses(text, "테스트")
    assert len(items) == 1
    assert items[0].alias == "판교타워"

def test_윗줄_건물명_추출():
    text = "LH성남권주거복지지사\n경기도 성남시 분당구 서현로 192"
    items = extract_addresses(text, "테스트")
    assert len(items) == 1
    assert items[0].alias == "LH성남권주거복지지사"

def test_긴_텍스트는_건물명_아님():
    # 30자 초과 → alias 없음
    text = "이것은건물명이아니라아주긴일반텍스트입니다여기서끝나지않습니다 경기도 성남시 분당구 서현로 192"
    items = extract_addresses(text, "테스트")
    assert items[0].alias == ""

def test_마침표_포함은_건물명_아님():
    text = "입주자를 모집합니다. 경기도 성남시 분당구 서현로 192"
    items = extract_addresses(text, "테스트")
    assert items[0].alias == ""

def test_건물명_없으면_빈문자열():
    text = "경기도 성남시 분당구 서현로 192"
    items = extract_addresses(text, "테스트")
    assert items[0].alias == ""
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
python3 -m pytest tests/test_text_parser.py::test_같은줄_앞_건물명_추출 tests/test_text_parser.py::test_윗줄_건물명_추출 -v
```
Expected: FAIL (alias == "")

- [ ] **Step 3: 구현**

`parser/text_parser.py` 전체를 다음으로 교체:
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

# 도로명 주소: 시도 시군구 [구] 도로명(로|길) 건물번호
_DOROMYEONG = re.compile(
    rf"({_SIDO})\s+"
    r"[\w가-힣]+[시군구]\s+"
    r"(?:[\w가-힣]+[구]\s+)?"
    r"[\w가-힣]+[로길]\s*"
    r"\d+(?:-\d+)?(?:\s+[\w가-힣\d]+동)?"
)

# 지번 주소: 시도 시군구 [구] 읍면동 번지
_JIBEON = re.compile(
    rf"({_SIDO})\s+"
    r"[\w가-힣]+[시군구]\s+"
    r"(?:[\w가-힣]+[구]\s+)?"
    r"[\w가-힣]+[읍면동리]\s+"
    r"\d+(?:-\d+)?"
)


def _normalize_addr(addr: str) -> str:
    """개행·연속 공백을 단일 공백으로 정규화."""
    return re.sub(r'\s+', ' ', addr).strip()


def _dedup_key(addr: str) -> str:
    """공백을 모두 제거한 중복 판별 키 (서현로 192 == 서현로192)."""
    return re.sub(r'\s', '', addr)


def _is_valid_alias(candidate: str) -> bool:
    """건물명으로 적합한지 판단."""
    if not candidate or len(candidate) > 30:
        return False
    # 문장 종결 부호가 있으면 일반 문장으로 판단
    if re.search(r'[.。!?]', candidate):
        return False
    # 숫자·기호·공백만이면 건물명 아님
    if re.match(r'^[\d\s\-()①②③④⑤⑥⑦⑧⑨⑩.,:]+$', candidate):
        return False
    return True


def _find_alias(text: str, match_start: int) -> str:
    """주소 매칭 위치 앞에서 건물명 후보를 추출.
    1순위: 같은 줄의 주소 앞 텍스트
    2순위: 바로 윗 줄 전체
    """
    # 같은 줄에서 주소 앞 텍스트
    line_start = text.rfind('\n', 0, match_start)
    line_start = line_start + 1 if line_start >= 0 else 0
    same_line_prefix = text[line_start:match_start].strip()

    if _is_valid_alias(same_line_prefix):
        return same_line_prefix

    # 바로 윗 줄
    if line_start > 0:
        prev_line_end = line_start - 1  # 앞 \n 직전
        prev_line_start = text.rfind('\n', 0, prev_line_end)
        prev_line_start = prev_line_start + 1 if prev_line_start >= 0 else 0
        prev_line = text[prev_line_start:prev_line_end].strip()
        if _is_valid_alias(prev_line):
            return prev_line

    return ""


def extract_addresses(text: str, source_prefix: str) -> List[AddressItem]:
    """텍스트에서 한국 주소(도로명+지번)를 추출하여 AddressItem 목록 반환."""
    found = []
    seen: set[str] = set()

    for pattern in (_DOROMYEONG, _JIBEON):
        for match in pattern.finditer(text):
            addr = _normalize_addr(match.group(0))
            key = _dedup_key(addr)
            if key not in seen:
                seen.add(key)
                alias = _find_alias(text, match.start())
                found.append(AddressItem(
                    raw_text=addr,
                    display_text=addr,
                    source_location=source_prefix,
                    alias=alias,
                ))

    return found
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
python3 -m pytest tests/test_text_parser.py -v
```
Expected: 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add parser/text_parser.py tests/test_text_parser.py
git commit -m "feat: 주소 앞 건물명 자동 추출 (_find_alias)"
```

---

### Task 3: `selectors.py` — 별명 입력 선택자 추가

**Files:**
- Modify: `naver/selectors.py`

별명 입력 UI는 저장 다이얼로그 내에 있으며 실제 UI 검증이 필요하다.
버튼 텍스트 기반 선택자를 우선 사용하고, UI 변경 시 이 파일만 수정한다.

- [ ] **Step 1: 선택자 추가**

`naver/selectors.py`의 `PLACE_SAVE_CONFIRM` 줄 아래에 추가:

```python
# 별명 입력 (저장 다이얼로그 내 — 리스트 선택 후 노출)
PLACE_SAVE_MEMO_BTN = "button:has-text('메모,별명')"   # '+ 메모,별명,URL 추가' 버튼
PLACE_SAVE_ALIAS_INPUT = "input.swt-input-text"        # 별명 입력란 (리스트명 input과 동일 클래스, 다이얼로그 컨텍스트에서 2번째)
```

> **Note:** `PLACE_SAVE_ALIAS_INPUT`의 정확한 선택자는 실제 Naver Maps UI에서 검증 필요.
> 저장 다이얼로그가 entryIframe 내부이므로 `entry_frame.fill(selector)` 컨텍스트에서 동작한다.

- [ ] **Step 2: 커밋**

```bash
git add naver/selectors.py
git commit -m "feat: 별명 입력 선택자 추가 (PLACE_SAVE_MEMO_BTN, PLACE_SAVE_ALIAS_INPUT)"
```

---

### Task 4: `map_saver.py` — 저장 시 별명 입력

**Files:**
- Modify: `naver/map_saver.py`
- Test: `tests/test_map_saver.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_map_saver.py` 끝에 추가:
```python
@pytest.mark.asyncio
async def test_save_in_entry_frame_별명_입력():
    """alias가 있으면 메모 버튼 클릭 후 alias 입력."""
    from naver.map_saver import _save_in_entry_frame

    page = AsyncMock()
    entry_frame = AsyncMock()
    list_item = AsyncMock()
    list_item.inner_text = AsyncMock(return_value="AUTO_20260405")
    entry_frame.query_selector_all = AsyncMock(return_value=[list_item])

    with patch("naver.map_saver._get_entry_frame", return_value=entry_frame):
        result = await _save_in_entry_frame(page, "AUTO_20260405", alias="판교타워")

    assert result is True
    # 메모 버튼 클릭 확인
    entry_frame.click.assert_any_call(pytest.approx, timeout=pytest.approx)  # 대략적 검증
    entry_frame.fill.assert_called()


@pytest.mark.asyncio
async def test_save_in_entry_frame_별명_없으면_메모버튼_안클릭():
    from naver.map_saver import _save_in_entry_frame

    page = AsyncMock()
    entry_frame = AsyncMock()
    list_item = AsyncMock()
    list_item.inner_text = AsyncMock(return_value="AUTO_20260405")
    entry_frame.query_selector_all = AsyncMock(return_value=[list_item])

    with patch("naver.map_saver._get_entry_frame", return_value=entry_frame):
        result = await _save_in_entry_frame(page, "AUTO_20260405", alias="")

    assert result is True
    # fill 호출 없음
    entry_frame.fill.assert_not_called()
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
python3 -m pytest tests/test_map_saver.py::test_save_in_entry_frame_별명_입력 tests/test_map_saver.py::test_save_in_entry_frame_별명_없으면_메모버튼_안클릭 -v
```
Expected: FAIL (unexpected keyword argument 'alias')

- [ ] **Step 3: `_save_in_entry_frame` 수정**

`naver/map_saver.py`의 `_save_in_entry_frame` 함수 시그니처와 리스트 클릭 이후 부분을 수정:

```python
async def _save_in_entry_frame(page, list_name: str, alias: str = "") -> bool:
    """entryIframe 내에서 저장 버튼 클릭 → 리스트 선택 → (별명 입력) → 저장 확인.
    Returns True on success, False on failure."""
```

리스트 아이템 클릭 후 confirm 클릭 전에 다음 블록 삽입 (기존 `await item.click()` 직후):
```python
                await item.click()
                await page.wait_for_timeout(500)
                if alias:
                    try:
                        await entry_frame.click(S.PLACE_SAVE_MEMO_BTN, timeout=3000)
                        await page.wait_for_timeout(300)
                        await entry_frame.fill(S.PLACE_SAVE_ALIAS_INPUT, alias)
                        await page.wait_for_timeout(300)
                    except Exception as ae:
                        print(f"[map_saver] 별명 입력 실패 (저장은 계속): {ae}", file=sys.stderr)
                await entry_frame.click(S.PLACE_SAVE_CONFIRM, timeout=3000)
                await page.wait_for_timeout(500)
                return True
```

- [ ] **Step 4: `_save_address_page` 수정**

시그니처 변경:
```python
async def _save_address_page(page, list_name: str, alias: str = "") -> bool:
```

리스트 아이템 클릭 후 confirm 클릭 전에 동일 블록 삽입:
```python
            if list_name in text:
                await item.click()
                await page.wait_for_timeout(500)
                if alias:
                    try:
                        await page.click(S.PLACE_SAVE_MEMO_BTN, timeout=3000)
                        await page.wait_for_timeout(300)
                        await page.fill(S.PLACE_SAVE_ALIAS_INPUT, alias)
                        await page.wait_for_timeout(300)
                    except Exception as ae:
                        print(f"[map_saver] 별명 입력 실패 (저장은 계속): {ae}", file=sys.stderr)
                await page.click(S.PLACE_SAVE_CONFIRM, timeout=3000)
                await page.wait_for_timeout(500)
                return True
```

- [ ] **Step 5: `_try_address_place`, `_save_one`, `save_one_by_index` 시그니처 전파**

```python
# _try_address_place
async def _try_address_place(page, list_name: str, alias: str = ""):
    ...
    ok = await _save_in_entry_frame(page, list_name, alias=alias)
    return ok

# _save_one
async def _save_one(page, address: str, list_name: str, alias: str = "") -> dict:
    ...
    # /address/ 분기
    place_result = await _try_address_place(page, list_name, alias=alias)
    ...
    success = await _save_address_page(page, list_name, alias=alias)
    ...
    # searchIframe 분기
    success = await _save_in_entry_frame(page, list_name, alias=alias)
    ...

# save_one_by_index — alias 불필요 (ambiguous 해소용), 변경 없음
```

- [ ] **Step 6: `save_addresses_to_naver`에서 alias 읽기**

`addr_dict`에서 alias 읽어 `_save_one`에 전달:
```python
        id_ = addr_dict["id"]
        display_text = addr_dict["display_text"]
        alias = addr_dict.get("alias", "")

        tab = await browser.new_page()
        try:
            result = await _save_one(tab, display_text, list_name, alias=alias)
        finally:
            await tab.close()
```

- [ ] **Step 7: 테스트 통과 확인**

```bash
python3 -m pytest tests/test_map_saver.py -v
```
Expected: 모두 PASS

- [ ] **Step 8: 커밋**

```bash
git add naver/map_saver.py tests/test_map_saver.py
git commit -m "feat: 저장 시 별명 입력 (alias 파라미터 전파)"
```

---

### Task 5: `static/index.html` — UI에 alias 입력란 추가

**Files:**
- Modify: `static/index.html`

- [ ] **Step 1: `renderList` 함수 수정**

`renderList` 함수 내 `li.innerHTML` 템플릿을 다음으로 교체:

```javascript
      li.innerHTML = `
        <span class="badge badge-${item.status}"${badgeExtra} onclick="openResolveModal('${item.id}')">${statusLabel(item.status)}</span>
        <input class="addr-text" value="${esc(item.display_text)}" data-id="${item.id}" onchange="updateText(this)">
        <input class="alias-text" value="${esc(item.alias||'')}" data-id="${item.id}"
          placeholder="건물명/별명" onchange="updateAlias(this)"
          style="width:120px;padding:4px 8px;border:1px solid #ddd;border-radius:6px;font-size:.8rem;color:#666;">
        <span class="source">${esc(item.source_location)}</span>
      `;
```

- [ ] **Step 2: `updateAlias` 함수 추가**

`updateText` 함수 바로 아래에 추가:

```javascript
  function updateAlias(input) {
    const item = addresses.find(a => a.id === input.dataset.id);
    if (item) item.alias = input.value;
  }
```

- [ ] **Step 3: `startSave` 페이로드에 alias 포함**

`startSave` 함수의 `.map()` 부분 수정:

```javascript
    const payload = addresses
      .filter(a => a.status !== 'unrecognized')
      .filter(a => listName ? true : (a.status !== 'success'))
      .map(a => ({id: a.id, display_text: a.display_text, alias: a.alias || ''}));
```

- [ ] **Step 4: 서버 재시작 후 수동 확인**

```bash
kill $(lsof -ti :8000) 2>/dev/null; sleep 1
python3 main.py > /tmp/navermap_server.log 2>&1 &
sleep 2 && open http://localhost:8000
```

PDF 업로드 → 주소 목록에 건물명 input 노출 여부 확인

- [ ] **Step 5: 커밋**

```bash
git add static/index.html
git commit -m "feat: 주소 목록에 별명 입력란 추가"
```

---

### Task 6: 전체 테스트 및 푸시

- [ ] **Step 1: 전체 테스트 실행**

```bash
python3 -m pytest tests/ -v
```
Expected: 모두 PASS

- [ ] **Step 2: 푸시**

```bash
git push origin master
```
