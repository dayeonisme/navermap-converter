# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

PDF·엑셀·텍스트에서 한국 주소를 추출하고 네이버 지도에 `AUTO_YYYYMMDD` 비공개 리스트를 자동 생성·저장하는 로컬 웹 앱. FastAPI 백엔드 + Playwright 브라우저 자동화 + 바닐라 JS 단일 페이지 UI.

## 개발 명령어

```bash
# 서버 실행
python main.py                        # http://localhost:8000

# 테스트 전체
pytest -v

# 단일 파일 테스트
pytest tests/test_text_parser.py -v

# 단일 테스트 함수
pytest tests/test_api.py::test_parse_text_주소_반환 -v

# 의존성 설치
pip install -r requirements.txt
playwright install chromium

# 테스트용 PDF 픽스처 재생성 (필요 시)
python tests/create_fixtures.py
```

## 아키텍처

### 데이터 흐름

```
파일/텍스트 입력
  → parser/ (text_parser, pdf_parser, excel_parser)
  → AddressItem 목록 (models.py)
  → main.py _item_registry (dict[str, AddressItem])
  → POST /save → asyncio.Task
  → naver/map_saver.py (리스트 생성 + 장소 순차 저장)
  → GET /progress SSE 스트림 → 웹 UI 실시간 업데이트
```

### 핵심 설계 결정

**싱글톤 잠금 모델:** `main.py`의 `_job_active: bool` 플래그로 동시 저장 요청을 차단한다. `asyncio.Lock.locked()`는 TOCTOU 경쟁 조건이 있어 사용하지 않음. 두 번째 `/save` 또는 `/retry` 요청은 409를 반환.

**SSE 진행 상황:** `/save` 호출은 202를 즉시 반환하고 실제 작업은 `asyncio.create_task()`로 백그라운드 실행. 클라이언트는 `/progress` SSE를 별도로 구독. `_progress_queue: asyncio.Queue`를 통해 task → SSE 스트림으로 이벤트 전달.

**세션 관리:** `naver/browser.py`는 Playwright 싱글톤. 로그인 상태는 `NID_AUT` 쿠키 존재 여부로 판단 (페이지 이동 없음). 로그인 필요 시 브라우저 창을 열고 쿠키 등장을 폴링 (최대 120초). 쿠키는 `sessions/naver_cookies.json`에 저장 (git 제외).

**주소 상태:** `pending → success | failed | ambiguous | unrecognized`. `ambiguous`는 재시도 불가 (검색 결과 복수 → UI 모달에서 수동 후보 선택). `failed`만 `/retry` 허용.

**건물명(별명) 자동 추출:** `parser/text_parser.py`의 `_find_alias()`가 주소 매칭 위치 기준으로 같은 줄 앞 텍스트 → 바로 윗 줄 순서로 건물명 후보를 탐색해 `AddressItem.alias`에 저장. `_is_valid_alias()`는 한글·알파벳 포함, 30자 이하, 문장 종결 부호 없음을 양성 조건으로 판단. UI에서 사용자가 수정 가능하며, 저장 시 네이버 지도 '+ 메모,별명,URL 추가' 버튼을 통해 별명으로 등록.

### 네이버 UI 선택자

`naver/selectors.py`에 모든 CSS 선택자를 상수로 집중 관리. 네이버 지도 UI 변경 시 이 파일만 수정. 선택자 실패는 해당 항목을 `failed`로 처리하고 배치는 계속 진행.

### 테스트 전략

- **파서/모델:** 실제 코드 단위 테스트
- **browser.py:** `AsyncMock`으로 Playwright 대체 (`_started = True`로 실제 브라우저 실행 방지)
- **API:** `fastapi.testclient.TestClient` (동기 모드)
- `pytest.ini`에 `asyncio_mode = auto` 설정됨 — `@pytest.mark.asyncio` 데코레이터 불필요

## SSE 이벤트 스키마

`/progress` SSE 스트림에서 전달되는 이벤트 타입:

| `type` | 설명 |
|--------|------|
| `trying_chrome_session` | Chrome 쿠키 임포트 시도 중 |
| `waiting_for_login` | 수동 로그인 대기 중 |
| `item_saved` | 개별 항목 저장 완료. `id`, `status`, `candidates` 필드 포함 |
| `cancelled` | 취소 완료 |
| `done` | 배치 완료. `summary` (성공/실패/ambiguous 카운트) 또는 `error` 필드 포함 |

## 알려진 이슈 / 다음 작업

- `PLACE_SAVE_ALIAS_INPUT` 선택자(`naver/selectors.py`)는 실제 Naver Maps 저장 다이얼로그에서 미검증 — 별명 입력 실패 시 저장은 계속 진행되며 stderr에 경고 출력
- OCR 사용 시 시스템에 Tesseract + `kor.traineddata` 별도 설치 필요
- Linux Chrome 쿠키 임포트는 Gnome Keyring / KDE Wallet 미지원 — Chrome이 시크릿 스토리지를 사용하지 않는 환경(비밀번호 없이 설치)에서만 동작
