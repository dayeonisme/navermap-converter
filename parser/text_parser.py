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

# 지번 주소: 시도 시군구 [구] 읍면동 번지
# 시군구 뒤에 선택적으로 구 단위가 올 수 있음 (예: 성남시 분당구 정자동)
_JIBEON = re.compile(
    rf"({_SIDO})\s+"
    r"[\w가-힣]+[시군구]\s+"
    r"(?:[\w가-힣]+[구]\s+)?"
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
