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
