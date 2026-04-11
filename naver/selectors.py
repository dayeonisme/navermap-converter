# naver/selectors.py
# 네이버 지도 자동화 선택자 — UI 변경 시 이 파일만 수정
#
# 프레임 구조 (검색 후 결과 클릭 시):
#   map.naver.com 메인                — 검색 입력, 내비 버튼
#   searchIframe (pcmap.place.naver.com/.../list) — 검색 결과 목록
#   entryIframe  (pcmap.place.naver.com/.../home) — 장소 상세 + 저장 다이얼로그
#   myPlaceBookmarkFolderListIframe (pages.map.naver.com) — 내 장소 패널 (저장 버튼 클릭 시)
#
# CSS Module 해시(UEzoS, TYaxT, VLTHu, YwYLL 등)는 네이버 배포 시 변경될 수 있음.
# UI 깨지면 이 파일부터 확인. swt-* 클래스는 디자인 시스템 클래스로 상대적으로 안정적.
# 마지막 검증일: 2026-04-12 (별명 입력 선택자 실제 UI 검증 완료)

# URLs
MAP_URL = "https://map.naver.com/p/"
SEARCH_URL = "https://map.naver.com/p/search/{query}"  # {query} = urllib.parse.quote(address)
NAVER_MAIN = "https://www.naver.com"

# 검색 (map.naver.com 메인 페이지)
SEARCH_INPUT = "input.input_search"
SEARCH_SUBMIT = "button.button_search"

# 검색 결과 (searchIframe 내부 — pcmap.place.naver.com/.../list)
# li.UEzoS: 일반 장소/음식점,  li.VLTHu: 교통/지하철 결과
SEARCH_RESULT_ITEM = "li.UEzoS, li.VLTHu"
# span.TYaxT: 일반 장소 이름,  span.YwYLL: 교통 결과 이름
SEARCH_RESULT_NAME = "span.TYaxT, span.YwYLL"
SEARCH_RESULT_ADDR = "span.suKMR"

# 장소 저장 (entryIframe 내부 — 검색 결과 클릭 후 나타남)
ENTRY_IFRAME = "entryIframe"
# 저장 버튼: aria-pressed 속성을 가진 D_Xqt (저장). a[href='#bookmark'] 은 구버전 선택자.
PLACE_SAVE_BUTTON = "a.D_Xqt[aria-pressed]"
PLACE_SAVE_LIST_ITEM = "button.swt-save-group-info"  # 리스트 선택 항목 (entryIframe 및 메인 DOM 공용)
PLACE_SAVE_CONFIRM = "button.swt-save-btn"  # 저장 확인 버튼

# 별명 입력 (저장 다이얼로그 내 — 리스트 선택 후 노출)
PLACE_SAVE_MEMO_BTN = "button.swt-save-add-info-btn"   # '메모, 별명, URL 추가' 버튼
PLACE_SAVE_ALIAS_INPUT = "input[placeholder='지도 위에 표시될 별명을 남겨주세요.']"  # 별명 입력란 (메모 패널 내 2번째 input)

# 주소 저장 (/address/ 페이지 — 메인 DOM에 렌더링, entryIframe 없음)
ADDRESS_SAVE_BUTTON = "button.btn_favorite"  # 주소 카드의 저장 버튼

# 내 장소 패널 (myPlaceBookmarkFolderListIframe 내부 — MY_PLACE_MENU 클릭 후)
MY_PLACE_MENU = "button.btn_navbar:has-text('저장')"  # 메인 페이지
MY_PLACE_IFRAME = "myPlaceBookmarkFolderListIframe"
CREATE_LIST_BUTTON = "button:has-text('새 리스트 만들기')"
LIST_NAME_INPUT = "input.swt-input-text"          # 폼의 첫 번째 input (리스트명)
LIST_PRIVACY_PRIVATE = "label.swt-save-folder-share-option-btn"  # 첫 번째 = 비공개
LIST_CONFIRM_BUTTON = "button.swt-complete-btn"
LIST_ITEM_SELECTOR = "button[class*='_list_item_']"  # 내 장소 패널의 리스트 항목
