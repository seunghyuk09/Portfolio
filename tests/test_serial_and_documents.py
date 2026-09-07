"""S/N 배정과 문서 조정 회귀."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.document_reconcile import (is_rounding_of, reconcile_dimension,
                                    reconcile_weight, unit_of)
from src.row_status import EXCLUDED, is_live, live_rows, sql_live
from src.serial_allocation import SerialRange, allocate, merge, release


def R(start, end, lot="L1", prefix="SN", width=4):
    return SerialRange(prefix, start, end, width, lot)


# ── S/N 배정 ────────────────────────────────────────────────

def test_한_조각으로_끝나면_한_줄로_나간다():
    배정, 남음 = allocate([R(1, 100)], 40)
    assert len(배정) == 1 and 배정[0].label == "SN0001 ~ SN0040"
    assert [r.label for r in 남음] == ["SN0041 ~ SN0100"]


def test_큰_조각부터_써서_행_수를_줄인다():
    """작은 것부터 쓰면 자투리가 늘고 패킹리스트 행도 늘어난다."""
    stock = [R(1, 10), R(101, 200), R(301, 320)]
    배정, _ = allocate(stock, 100)
    assert len(배정) == 1, "100개짜리 조각 하나로 끝나야 한다"


def test_모자라면_거절한다():
    with pytest.raises(ValueError, match="재고 부족"):
        allocate([R(1, 10)], 50)


def test_되돌아온_조각은_도로_합친다():
    남은재고 = [R(1, 40), R(71, 100)]
    돌아옴 = [R(41, 70)]
    assert [r.label for r in release(남은재고, 돌아옴)] == ["SN0001 ~ SN0100"]


def test_로트가_다르면_안_합친다():
    """번호가 이어져도 물건이 다르다. 패킹리스트에서 구분해 보여줘야 한다."""
    합침 = merge([R(1, 50, lot="L1"), R(51, 100, lot="L2")])
    assert len(합침) == 2


def test_접두가_다르면_안_합친다():
    합침 = merge([R(1, 50, prefix="SN"), R(51, 100, prefix="AB")])
    assert len(합침) == 2


# ── 문서 ↔ DB 조정 ──────────────────────────────────────────

def test_반올림이면_계산값을_지키고_알린다():
    """문서 4.8 vs 계산 4.84 — 사람이 편의상 줄여 적은 것이다."""
    d = reconcile_weight(4.8, 4.84)
    assert d.apply is False and d.value == 4.84
    assert d.notice, "조용히 넘기면 문서를 고칠 기회가 사라진다"


def test_진짜_다른_값이면_문서를_따른다():
    d = reconcile_weight(5.20, 4.84)
    assert d.apply is True and d.value == 5.20 and not d.notice


def test_빈칸은_채우고_문서가_비면_안_지운다():
    assert reconcile_weight(4.8, None).apply is True
    assert reconcile_weight(None, 4.84).apply is False


def test_문서가_더_정밀하면_반영한다():
    assert reconcile_weight(4.84, 4.8).apply is True


def test_단위_판정은_끝에_붙은_글자만_본다():
    """치수 구분자 'X' 도 알파벳이다 — 이걸 틀려서 회귀가 빨개진 적이 있다."""
    assert unit_of("570 X 260 X 195") == ""
    assert unit_of("570 X 260 X 195mm") == "mm"
    assert unit_of("57 X 26 X 19cm") == "cm"


def test_문서에_단위가_빠져도_DB_표기를_안_무너뜨린다():
    d = reconcile_dimension("570 X 260 X 195", "570 X 260 X 195mm")
    assert d.apply is False and d.notice


def test_DB가_단위를_잃었으면_되돌린다():
    d = reconcile_dimension("570 X 260 X 195", "570 X 260 X 195")
    assert d.apply is True and d.value == "570 X 260 X 195mm"


def test_발주별_메모는_살린다():
    d = reconcile_dimension("500 X 200 X 100", "570 X 260 X 195mm // 특수포장")
    assert "특수포장" in str(d.value)


def test_반올림_판정():
    assert is_rounding_of(4.8, 4.84) is True
    assert is_rounding_of(4.9, 4.84) is False


# ── 행 상태 ────────────────────────────────────────────────

def test_껍데기_행은_세지_않는다():
    rows = [{"행상태": "정상"}, {"행상태": "정정잉여"}, {"행상태": None}]
    assert len(live_rows(rows)) == 2, "None 은 정상으로 본다(옛 행)"


def test_SQL_조각이_파이썬_규칙과_같다():
    """한 곳에서만 정의한다 — 갈라지면 화면과 DB 가 다른 답을 낸다."""
    frag = sql_live()
    for s in EXCLUDED:
        assert f"'{s}'" in frag
        assert is_live(s) is False
