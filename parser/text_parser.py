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
