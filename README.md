# 네이버 지도 주소 변환기

PDF·엑셀·텍스트 파일에서 한국 주소를 추출하고, 네이버 지도에 `AUTO_YYYYMMDD` 비공개 리스트를 생성하여 장소를 자동 저장하는 로컬 웹 앱.

---

## 구현 현황

### 완료
- [x] `models.py` — `AddressItem` 공유 데이터 모델
- [x] `parser/text_parser.py` — 도로명/지번 정규식 주소 추출
- [x] `parser/pdf_parser.py` — PDF 텍스트 추출 + OCR 폴백
- [x] `parser/excel_parser.py` — 엑셀/CSV 파싱, 주소 컬럼 자동 감지
- [x] `naver/selectors.py` — 네이버 지도 CSS 선택자 상수
- [x] `naver/browser.py` — Playwright 싱글톤, 세션/로그인 관리
- [x] `naver/map_saver.py` — 리스트 생성 + 장소 저장 자동화
- [x] `main.py` — FastAPI 앱 (upload / parse-text / save / retry / progress / login-status)
- [x] `static/index.html` — 단일 페이지 웹 UI (SSE 진행 상황 실시간 표시)
- [x] `tests/` — 파서·모델·API·브라우저 단위/통합 테스트

### 남은 작업 / 확인 필요 사항

| 항목 | 내용 |
|------|------|
| **실제 UI 동작 테스트** | `naver/selectors.py`의 CSS 선택자가 현재 네이버 지도 UI와 일치하는지 실제 브라우저로 검증 필요 (네이버가 UI를 변경했을 가능성 있음) |
| **`pdf2image` 누락** | `requirements.txt`에 `pdf2image`가 없음. OCR 폴백 사용 시 필요 → `pip install pdf2image` 후 `requirements.txt`에 추가 |
| **Tesseract 설치** | OCR 기능을 쓰려면 시스템에 Tesseract와 `kor.traineddata`를 별도 설치해야 함 (아래 가이드 참고) |
| **ambiguous 수동 처리 UI** | 검색 결과가 복수인 경우 UI에서 수동 선택하는 기능 미구현 (현재는 목록에 `ambiguous`로 표시만 함) |

---

## 빠른 시작

### 1. 사전 요구사항

- Python 3.10 이상
- Tesseract OCR (OCR 폴백 필요 시)

  **Windows:**
  ```
  https://github.com/UB-Mannheim/tesseract/wiki 에서 설치 파일 다운로드
  설치 시 "Additional language data" → Korean 선택
  ```
  설치 후 환경변수 PATH에 Tesseract 경로 추가 (예: `C:\Program Files\Tesseract-OCR`)

### 2. 저장소 클론 및 설치

```bash
git clone <repo-url>
cd navermap_converter

# 패키지 설치
pip install -r requirements.txt
pip install pdf2image   # requirements.txt에 아직 미포함, 별도 설치 필요

# Playwright 브라우저 설치
playwright install chromium
```

### 3. 실행

```bash
python main.py
```

브라우저에서 `http://localhost:8000` 접속.

#### macOS: 더블클릭 런처 (선택)

매번 터미널에서 `python main.py`를 치기 번거로우면 토글 앱을 빌드한다.

```bash
bash launcher/build.sh    # 저장소 루트에 NaverMap.app 생성
```

- **NaverMap** 더블클릭 → 서버 켜짐(Terminal 창에 로그 표시) + 브라우저 자동 오픈
- 다시 더블클릭 → 서버 꺼짐 + 창 닫힘 (켜짐 ↔ 꺼짐 토글)
- Terminal 창 존재 여부 = 서버 실행 중 여부
- Dock 고정: `NaverMap.app`을 Dock(구분선 왼쪽)으로 드래그
- 첫 실행 시 macOS가 "Terminal 제어" 권한을 물으면 허용

> **끄기는 아이콘을 다시 클릭**한다 (경고창 없이 종료 + 창 닫힘). Terminal 창을 빨간 버튼/⌘W로 직접 닫으면 "실행 중 프로세스 종료" 확인창이 뜰 수 있다 — 이는 Terminal 기본 동작이며, 끄려면 Terminal ▸ 설정 ▸ 프로파일 ▸ (사용 중인 프로파일) ▸ 셸 ▸ "종료 전 확인 → 없음"으로 변경.

> `NaverMap.app`은 빌드 산출물이라 git에 포함하지 않는다 — `launcher/`의 소스로 언제든 재생성.

### 4. 테스트 실행

```bash
pytest -v
```

> `tests/test_api.py`의 PDF 업로드 테스트는 Windows 시스템 폰트(`C:/Windows/Fonts/malgun.ttf`)를 사용합니다. macOS/Linux에서는 해당 테스트가 폰트 없이 실행되지만 통과됩니다.

---

## 아키텍처

```
navermap_converter/
├── main.py                  # FastAPI 앱 진입점, 모든 API 라우터
├── models.py                # AddressItem 공유 데이터 모델
├── requirements.txt         # Python 의존성
├── pytest.ini               # asyncio_mode = auto
├── parser/
│   ├── text_parser.py       # 한국 주소 정규식 추출 (도로명 + 지번)
│   ├── pdf_parser.py        # pdfplumber 텍스트 추출 + OCR 폴백
│   └── excel_parser.py      # .xlsx/.xls/.csv 파싱, 주소 컬럼 자동 감지
├── naver/
│   ├── selectors.py         # 네이버 지도 CSS 선택자 상수 (UI 변경 시 이 파일만 수정)
│   ├── browser.py           # Playwright 싱글톤, 세션 쿠키 저장/로드, 로그인 대기
│   └── map_saver.py         # 네이버 지도 리스트 생성 + 장소 저장 자동화
├── static/
│   └── index.html           # 단일 페이지 웹 UI
├── launcher/                # macOS 더블클릭 런처 (build.sh → NaverMap.app)
│   ├── build.sh             # 빌드: applescript 컴파일 + 아이콘 적용
│   ├── NaverMap.applescript # 토글 런처 소스 (서버 켜짐 ↔ 꺼짐)
│   ├── make_icon.py         # 앱 아이콘(네이버 그린 + 위치 핀) 생성
│   └── seticon.swift        # 커스텀 아이콘 주입 (캐시 무시)
├── tests/
│   ├── test_models.py
│   ├── test_text_parser.py
│   ├── test_pdf_parser.py
│   ├── test_excel_parser.py
│   ├── test_browser.py      # mock 기반 단위 테스트
│   ├── test_api.py          # FastAPI 엔드포인트 통합 테스트
│   ├── create_fixtures.py   # 테스트용 PDF 픽스처 생성 스크립트
│   └── fixtures/
│       └── sample_text.pdf
├── sessions/                # 네이버 로그인 쿠키 저장 폴더 (git 제외)
│   └── .gitkeep
└── docs/
    └── superpowers/
        ├── specs/2026-03-22-navermap-converter-design.md   # 설계 문서
        └── plans/2026-03-22-navermap-converter.md          # 구현 계획
```

---

## API 요약

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/upload` | PDF·엑셀·CSV 파일 업로드 → 주소 목록 반환 |
| `POST` | `/parse-text` | 자유 텍스트 → 주소 목록 반환 |
| `POST` | `/save` | 주소 목록 저장 시작 (202 Accepted, SSE로 진행 상황 전달) |
| `POST` | `/retry` | `failed` 상태 항목 재시도 |
| `GET`  | `/progress` | SSE 스트림 (저장 진행 상황 실시간) |
| `GET`  | `/login-status` | 네이버 로그인 여부 확인 |

---

## 사용 흐름

1. `python main.py` 실행 → `http://localhost:8000` 접속
2. 파일 업로드 또는 텍스트 붙여넣기
3. 추출된 주소 목록 확인·인라인 편집
4. "저장 시작" 클릭
   - 세션 쿠키 유효 → 즉시 저장
   - 세션 없음/만료 → Playwright 브라우저 창 열림 → 네이버에 수동 로그인 → 저장 시작
5. SSE로 실시간 진행 상황 확인
6. 완료 후 성공/실패/ambiguous 요약 표시

---

## 개발 참고사항

**네이버 UI 변경 대응:**
- `naver/selectors.py` 파일의 CSS 선택자만 수정하면 됨
- 브라우저 자동화가 실패하면 먼저 이 파일을 확인

**동시 저장 방지:**
- 싱글톤 `_job_active` 플래그로 동시 저장 요청 차단 (두 번째 요청은 409 반환)

**세션 보안:**
- `sessions/naver_cookies.json`은 실제 네이버 인증 토큰 포함
- `.gitignore`에 `sessions/` 폴더 제외 처리됨 — 절대 커밋 금지

**ambiguous 처리:**
- 검색 결과 복수 시 자동 선택 없이 `ambiguous` 상태로 표시
- 현재는 사용자가 네이버 지도에서 직접 수동 처리해야 함
