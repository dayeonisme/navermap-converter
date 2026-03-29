from models import AddressItem


def test_기본값_status_pending():
    item = AddressItem(display_text="서울", raw_text="서울", source_location="테스트")
    assert item.status == "pending"


def test_id_자동_생성():
    a = AddressItem(display_text="a", raw_text="a", source_location="x")
    b = AddressItem(display_text="b", raw_text="b", source_location="x")
    assert a.id != b.id
    assert len(a.id) == 36  # UUID 형식


def test_to_dict_필드():
    item = AddressItem(display_text="서울특별시 강남구 테헤란로 152", raw_text="raw", source_location="PDF 1페이지")
    d = item.to_dict()
    assert set(d.keys()) == {"id", "raw_text", "display_text", "source_location", "status", "candidates"}
    assert d["display_text"] == "서울특별시 강남구 테헤란로 152"
    assert d["status"] == "pending"


def test_candidates_기본값_빈_리스트():
    item = AddressItem(display_text="서울", raw_text="서울", source_location="테스트")
    assert item.candidates == []


def test_to_dict_candidates_포함():
    item = AddressItem(display_text="서울", raw_text="서울", source_location="테스트")
    item.candidates = [{"name": "서울역", "address": "서울 중구"}]
    d = item.to_dict()
    assert d["candidates"] == [{"name": "서울역", "address": "서울 중구"}]
