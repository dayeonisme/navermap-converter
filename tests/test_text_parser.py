# tests/test_text_parser.py
import pytest
from parser.text_parser import extract_addresses

def test_도로명_주소_추출():
    text = "서울특별시 강남구 테헤란로 152"
    results = extract_addresses(text, source_prefix="테스트")
    assert len(results) == 1
    assert results[0].display_text == "서울특별시 강남구 테헤란로 152"
    assert results[0].source_location == "테스트"
    assert results[0].status == "pending"

def test_지번_주소_추출():
    text = "경기도 성남시 분당구 정자동 6-1"
    results = extract_addresses(text, source_prefix="테스트")
    assert len(results) == 1
    assert results[0].display_text == "경기도 성남시 분당구 정자동 6-1"

def test_여러_주소_추출():
    text = """
    서울특별시 마포구 월드컵북로 396
    부산광역시 해운대구 해운대해변로 264
    """
    results = extract_addresses(text, source_prefix="테스트")
    assert len(results) == 2

def test_주소_없는_텍스트():
    text = "안녕하세요 이것은 주소가 없는 텍스트입니다"
    results = extract_addresses(text, source_prefix="테스트")
    assert len(results) == 0

def test_인식불가_항목은_반환되지_않음():
    text = "1234 이상한 텍스트"
    results = extract_addresses(text, source_prefix="테스트")
    assert len(results) == 0

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

def test_기호만_앞텍스트는_건물명_아님():
    # 순수 기호만 있는 경우
    text = "※→# 경기도 성남시 분당구 서현로 192"
    items = extract_addresses(text, "테스트")
    assert items[0].alias == ""
