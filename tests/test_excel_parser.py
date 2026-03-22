# tests/test_excel_parser.py
import pytest
from pathlib import Path
from openpyxl import Workbook
from parser.excel_parser import parse_excel

def make_xlsx(path, data: dict):
    wb = Workbook()
    ws = wb.active
    headers = list(data.keys())
    ws.append(headers)
    for row in zip(*data.values()):
        ws.append(list(row))
    wb.save(path)

def test_주소_컬럼_자동_감지(tmp_path):
    f = tmp_path / "test.xlsx"
    make_xlsx(f, {
        "이름": ["홍길동", "김철수"],
        "주소": ["서울특별시 강남구 테헤란로 152", "경기도 수원시 팔달구 효원로 1"],
        "전화": ["010-1234-5678", "010-9876-5432"],
    })
    items = parse_excel(f)
    assert len(items) == 2
    assert any("테헤란로" in i.display_text for i in items)

def test_source_location_형식(tmp_path):
    f = tmp_path / "test.xlsx"
    make_xlsx(f, {"주소": ["서울특별시 강남구 테헤란로 152"]})
    items = parse_excel(f)
    assert len(items) == 1
    assert "행" in items[0].source_location

def test_매칭률_50미만_빈_결과(tmp_path):
    f = tmp_path / "test.xlsx"
    make_xlsx(f, {
        "이름": ["홍길동", "김철수", "박영희"],
        "코드": ["A001", "B002", "C003"],
    })
    items = parse_excel(f)
    assert len(items) == 0

def test_csv_파싱(tmp_path):
    f = tmp_path / "test.csv"
    f.write_text("이름,주소\n홍길동,서울특별시 마포구 월드컵북로 396\n", encoding="utf-8")
    items = parse_excel(f)
    assert len(items) == 1
    assert "월드컵북로" in items[0].display_text
