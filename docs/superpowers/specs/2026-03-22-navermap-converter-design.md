# 네이버 지도 주소 변환기 설계 문서

**날짜:** 2026-03-22
**상태:** 확정

---

## 개요

PDF, 엑셀/CSV, 텍스트 등 다양한 형태의 주택 주소 데이터를 입력받아 네이버 지도에 `AUTO_YYYYMMDD` 형식의 비공개 리스트를 생성하고 장소를 자동 추가하는 로컬 웹 애플리케이션.

---

## 기술 스택

- **백엔드:** Python 3.10+, FastAPI
- **웹 UI:** HTML/CSS/JS (단일 페이지, 외부 프레임워크 없음)
- **PDF 파싱:** pdfplumber (텍스트 추출), pdf2image + pytesseract (OCR 폴백)
- **엑셀/CSV 파싱:** openpyxl, pandas
- **브라우저 자동화:** Playwright (Chromium, async_api)
- **세션 관리:** Playwright 쿠키 파일 (sessions/naver_cookies.json)
- **의존성 관리:** requirements.txt

---

## 디렉토리 구조

```
navermap_converter/
├── main.py                    # FastAPI 앱 진입점, API 라우터
├── requirements.txt
├── .gitignore                 # sessions/ 폴더 제외
├── parser/
│   ├── pdf_parser.py          # PDF 텍스트 추출 + OCR 폴백
│   ├── excel_parser.py        # 엑셀/CSV 파싱
│   └── text_parser.py         # 자유 텍스트에서 한국 주소 패턴 추출
├── naver/
│   ├── browser.py             # Playwright 브라우저 관리, 세션 저장/로드
│   ├── map_saver.py           # 네이버 지도 "내 장소" 저장 자동화
│   └── selectors.py           # 네이버 지도 CSS 선택자 상수 (한 곳에서 관리)
├── static/
│   └── index.html             # 단일 페이지 웹 UI
└── sessions/
    └── naver_cookies.json     # 로그인 세션 쿠키 (자동 생성, git 제외)
```

---

## 주소 데이터 모델

파이프라인 전체에서 공유하는 단일 주소 객체:

```python
{
    "id": str,               # UUID, 진행 추적 및 재시도용
    "raw_text": str,         # 파싱 원문 (감사 목적)
    "display_text": str,     # 사용자가 편집 가능한 텍스트
    "source_location": str,  # 출처 (예: "PDF 3페이지", "엑셀 B열 5행")
    "status": str            # "pending" | "success" | "failed" | "unrecognized" | "ambiguous"
}
```

---

## API 엔드포인트

### `POST /upload`
- **요청:** `multipart/form-data`, 필드명 `file`
- **허용 형식:** `.pdf`, `.xlsx`, `.xls`, `.csv`
- **최대 크기:** 50MB
- **응답:**
```json
{
    "addresses": [{ "id": "...", "raw_text": "...", "display_text": "...", "source_location": "...", "status": "pending" }]
}
```
- **오류:** 지원하지 않는 형식 → 422, 파싱 실패 → 500

### `POST /parse-text`
- **요청:**
```json
{ "text": "자유 텍스트..." }
```
- **응답:** `/upload`와 동일한 addresses 배열

### `POST /save`
- **요청:**
```json
{
    "addresses": [{ "id": "...", "display_text": "..." }]
}
```
- **응답:** `202 Accepted` (즉시 반환, 실제 저장은 SSE로 진행 상황 전달)

### `GET /progress`
- **방식:** Server-Sent Events (SSE)
- **이벤트 형식:**
```json
{ "id": "...", "status": "success" | "failed" | "ambiguous", "message": "선택적 메시지" }
```
- 저장 완료 후 `{ "type": "done", "summary": { "success": N, "failed": N, "ambiguous": N } }` 전송
- 이벤트는 재연결 시 재전송되지 않음 — 클라이언트는 배치 전체 동안 연결을 유지해야 함
- 싱글톤 잠금 모델로 인해 항상 단일 활성 작업만 존재하므로 job ID 없이 `/progress`는 항상 현재 진행 중인 작업에 대응함
- 저장 시작 전 로그인 대기 중: `{ "type": "waiting_for_login" }` 이벤트 전송
- `/save`나 `/retry` 호출 전에 클라이언트가 연결하면 즉시 연결 종료 (empty stream close)

### `POST /retry`
- **요청:** `{ "ids": ["...", "..."] }` (재시도할 항목 ID 목록)
- **허용 status:** `"failed"` 상태 항목만 허용; `"ambiguous"` 항목은 재시도 허용 안 됨 (수동 처리 필요)
- **오류:** 존재하지 않는 ID 또는 허용되지 않는 status의 ID → 422 반환 (거부된 ID 목록 포함)
- **응답:** `202 Accepted`, 이후 `/progress` SSE로 진행
- `/save`와 동일한 `asyncio.Lock`을 획득함 — 저장 또는 재시도가 이미 진행 중이면 409 반환

### `GET /login-status`
- **응답:** `{ "logged_in": true | false }`

---

## 사용자 흐름

1. `python main.py` 실행 → 브라우저에서 `http://localhost:8000` 접속
2. 파일 업로드 또는 텍스트 붙여넣기
3. 서버가 파싱 → 추출된 주소 목록 표시 (출처, 상태 포함)
4. 사용자가 목록 확인/수정 (인라인 편집 가능)
5. "저장 시작" 클릭 → `POST /save`
6. **로그인 흐름:**
   - 세션 쿠키 유효 → 즉시 저장 시작
   - 세션 없음 또는 만료 → Playwright 브라우저 창 열림, UI에 "로그인 창에서 네이버에 로그인 후 완료 버튼을 누르세요" 표시
   - Playwright가 `NID_AUT` 쿠키 등장을 폴링하여 로그인 완료 감지 (최대 120초)
   - 로그인 창 닫힘 → 저장 시작
7. 각 주소를 순차적으로 저장, SSE로 진행 상황 전달
8. 완료 후 성공/실패/ambiguous 요약 표시

---

## 모듈 상세

### parser/pdf_parser.py
- pdfplumber로 텍스트 추출 시도
- 페이지별 텍스트가 비어있으면 pdf2image로 이미지 변환 후 pytesseract OCR (한국어 + 영어)
- 추출된 텍스트를 `text_parser.parse()`에 전달
- `source_location`에 페이지 번호 기록

### parser/excel_parser.py
- .xlsx/.xls: openpyxl, .csv: pandas
- 멀티 시트 `.xlsx`는 첫 번째 시트만 처리
- 주소 컬럼 식별 전략: 각 컬럼에 대해 한국 주소 정규식 매칭 비율 계산, 가장 높은 컬럼 자동 선택
- 매칭률 50% 미만인 경우 해당 컬럼 전체를 "인식 불가"로 표시하고 사용자에게 알림
- `source_location`에 열 이름 + 행 번호 기록

### parser/text_parser.py
- 한국 주소 두 형식 모두 지원:
  - **도로명 주소:** `[시도] [시군구] [도로명로/길] [건물번호]`
  - **지번 주소:** `[시도] [시군구] [읍면동] [번지]`
- 정규식으로 두 패턴 탐색, 매칭 실패 시 `status: "unrecognized"`

### naver/selectors.py
- 네이버 지도 자동화에 사용하는 모든 CSS 선택자/XPath를 상수로 관리
- 네이버 UI 변경 시 이 파일만 수정하면 됨
- 예: `SEARCH_INPUT = "input#query"`, `SAVE_BUTTON = "..."`

### naver/browser.py
- Playwright async_api 기반 싱글톤 브라우저 인스턴스
- `POST /save` 진입 시 락(asyncio.Lock) 획득 → 동시 저장 요청 방지 (두 번째 요청은 409 반환)
- 세션 쿠키 저장/로드 (sessions/naver_cookies.json)
- 로그인 상태 확인: 네이버 메인 접속 후 로그인 쿠키(`NID_AUT`) 존재 여부 확인
- 로그인 필요 시 Playwright 창을 foreground로 열고, `NID_AUT` 쿠키 등장까지 대기 (최대 120초)

### naver/map_saver.py
- **배치 시작 전:** 네이버 지도에서 새 리스트 생성
  - 리스트 이름: `AUTO_YYYYMMDD` (데이터 업로드 일자 기준, 예: `AUTO_20260322`)
  - 공개 범위: 비공개
  - 색상: 임의 (기본값 사용)
- 주소 검색 → 결과 수 확인:
  - 결과 1개: 생성된 리스트에 장소 추가 → `status: "success"`
  - 결과 0개: `status: "failed"`
  - 결과 복수: **`status: "ambiguous"`** 로 표시하고 건너뜀 (자동 선택 없음)
- 배치 완료 후 ambiguous 항목을 별도 목록으로 표시, 사용자가 수동 처리 가능
- 선택자 접근은 모두 `selectors.py`를 통해서만

### static/index.html
- 파일 업로드 영역 (드래그앤드롭 + 클릭)
- 텍스트 붙여넣기 영역
- 추출된 주소 목록 (상태 배지 + 인라인 편집)
- 저장 진행 상황 (진행바 + 항목별 상태 실시간 업데이트, SSE 사용)
- 완료 요약 (성공 N개 / 실패 N개 / 모호 N개)
- 실패/모호 항목 재시도 버튼 (실패 항목만 재시도)

---

## 에러 처리

| 상황 | 처리 방법 |
|------|----------|
| PDF 스캔본 | 자동 OCR 전환 |
| OCR 주소 인식 실패 | `status: "unrecognized"`, 사용자 수동 편집 가능 |
| 세션 만료 | `NID_AUT` 쿠키 확인 후 로그인 재요청 |
| 주소 검색 결과 없음 | `status: "failed"`, 다음 주소 계속 진행 |
| 검색 결과 복수 | `status: "ambiguous"`, 자동 선택 없이 사용자에게 위임 |
| 리스트 생성 실패 | 배치 전체 중단, 오류 메시지 표시 |
| 네이버 UI 선택자 실패 | 해당 항목 `failed` 처리, 배치 중단 없이 계속 진행 |
| 저장 오류 | `status: "failed"`, 재시도 버튼 제공 (실패 항목만) |
| 동시 저장 요청 | 409 반환, UI에 "이미 저장 중" 메시지 |
| 로그인 타임아웃 (120초) | 저장 취소, 오류 메시지 표시 |
| 지원하지 않는 파일 형식 | 422 오류, UI에 안내 메시지 |

---

## 세션 파일 보안

- `sessions/naver_cookies.json`은 실제 네이버 계정 인증 토큰 포함
- `.gitignore`에 `sessions/` 추가 필수
- 로컬 전용 도구로 외부 배포 금지

---

## 외부 의존성 및 설치 요구사항

- Python 3.10+
- Tesseract OCR 엔진 (로컬 설치 필요, `kor.traineddata` 포함)
- Playwright Chromium: `playwright install chromium`
- Python 패키지: `requirements.txt` 참조

---

## 범위 밖 (Out of Scope)

- 네이버 외 지도 서비스 지원
- 스캔본 이미지 파일 직접 입력 (PDF 내 이미지는 지원)
- 대량(500개 이상) 처리 최적화
- 외부 서버 배포
- 검색 결과 복수일 때 UI 내에서 직접 선택 (수동 처리로 위임)
