# 주소 결과 직접 저장 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 네이버 지도 `/address/` 검색 결과를 인근 장소가 아닌 주소 자체로 저장한다.

**Architecture:** `_save_one`의 주소 결과 분기는 `_save_address_page`만 호출한다. 기존 주소 카드 저장과 리스트 선택 로직은 재사용하며, 주변 장소 진입 함수는 일반 검색 흐름에 관여하지 않는다.

**Tech Stack:** Python 3.9, pytest, Playwright async mocks.

## Global Constraints

- `/address/` 결과는 `button.btn_favorite` 주소 저장 버튼을 사용한다.
- 주소 저장 시 외부 네이버 리스트에 새 데이터를 만들지 않는 자동화 테스트를 사용한다.
- 일반 검색 결과, 로그인, 리스트 생성 로직을 변경하지 않는다.

---

### Task 1: 주소 결과 직접 저장 회귀 테스트와 구현

**Files:**
- Modify: `tests/test_map_saver.py`
- Modify: `naver/map_saver.py`

**Interfaces:**
- Consumes: `_save_one(page, address, list_name, alias="") -> dict`
- Produces: `/address/` URL에서 `_save_address_page(page, list_name, alias)`를 호출하고 성공 상태를 반환하는 동작

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_save_one_address_result_saves_address_without_opening_nearby_place(monkeypatch):
    page = FakePage(url="https://map.naver.com/p/search/x/address/example")
    saved = []

    async def save_address(actual_page, list_name, alias=""):
        saved.append((actual_page, list_name, alias))
        return True

    async def open_nearby(*args, **kwargs):
        raise AssertionError("주소 결과에서 주변 장소를 열면 안 됩니다")

    monkeypatch.setattr(map_saver, "_save_address_page", save_address)
    monkeypatch.setattr(map_saver, "_try_address_place", open_nearby)

    result = await map_saver._save_one(page, "서울 종로구 필운동 202", "검증 리스트")

    assert result == {"status": "success", "candidates": []}
    assert saved == [(page, "검증 리스트", "")]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_map_saver.py::test_save_one_address_result_saves_address_without_opening_nearby_place -v`

Expected: FAIL because `_save_one` currently calls `_try_address_place` first.

- [ ] **Step 3: Write minimal implementation**

```python
if "/address/" in page.url:
    success = await _save_address_page(page, list_name, alias=alias)
    return {"status": "success" if success else "failed", "candidates": []}
```

- [ ] **Step 4: Run focused test and full suite**

Run: `pytest tests/test_map_saver.py::test_save_one_address_result_saves_address_without_opening_nearby_place -v && pytest -q`

Expected: focused test PASS and full suite PASS.

- [ ] **Step 5: Commit**

```bash
git add naver/map_saver.py tests/test_map_saver.py
git commit -m "fix: 주소 결과를 직접 저장"
```
