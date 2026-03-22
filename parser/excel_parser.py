# parser/excel_parser.py
from pathlib import Path
from typing import List
import re
import pandas as pd
from models import AddressItem
from parser.text_parser import extract_addresses, _DOROMYEONG, _JIBEON

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
            items.append(AddressItem(
                raw_text=str(value),
                display_text=str(value),
                source_location=source,
                status="unrecognized",
            ))
    return items
