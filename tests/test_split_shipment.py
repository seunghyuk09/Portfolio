"""분할출고 잔여 계산 회귀.

핵심은 ③ 이다 — **취소했다가 줄여서 다시 확정한 뒤** 잔여가 얼마로 나오는가.
실제로 그 경로에서 100개가 붕 떴다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.split_shipment import (Batch, ShipmentRecord, analyze, next_sequence,
                                remaining, split_mode)


def _batch(seq, state, requested, shipped, cancelled_qty=0):
    recs = [ShipmentRecord("PRD-1001", shipped)]
    if cancelled_qty:
        recs.append(ShipmentRecord("PRD-1001", cancelled_qty, cancelled=True))
    return Batch(seq=seq, state=state, requested={"PRD-1001": requested},
                 shipments=recs)


def test_보통은_요청과_실출고가_같다():
    batches = [_batch(1, "출고확정", 400, 400)]
    assert remaining({"PRD-1001": 1000}, batches) == {"PRD-1001": 600}


def test_취소된_차수는_아예_안_센다():
    """취소된 차수에 **출고 이력이 남아 있어도** 세지 않는다.

    ★ 처음엔 취소 차수를 shipments 없이 만들었더니, 그 차수를 계산에 포함시켜도
      결과가 안 변해서 이 테스트가 아무것도 지키지 않았다. 돌연변이 하네스가
      잡아줬다. 취소돼도 출고 이력 행 자체는 남으므로(지우지 않는다) 실제
      데이터에 가까운 모양은 이쪽이다.
    """
    batches = [
        _batch(1, "출고확정", 400, 400),
        _batch(2, "완전취소", 250, 250),      # 이력이 남아 있다
    ]
    assert remaining({"PRD-1001": 1000}, batches) == {"PRD-1001": 600}, \
        "취소 차수의 250 을 세면 350 이 되어 버린다"


def test_취소_후_줄여서_재확정하면_실출고를_따른다():
    """★ 이 케이스 때문에 기준을 바꿨다.

    1차에 400 을 걸었다가 취소하고, 300 으로 줄여 다시 확정했다.
    '걸어둔 수량'(requested) 은 400 그대로다 — 아무도 줄이지 않는다.
    실제로 나간 건 300 이므로 잔여는 700 이어야 한다.
    """
    batches = [_batch(1, "출고확정", requested=400, shipped=300, cancelled_qty=100)]

    assert remaining({"PRD-1001": 1000}, batches) == {"PRD-1001": 700}

    # 옛 기준(걸어둔 수량)이었다면 600 이 나와 100개가 붕 떴다
    옛방식 = 1000 - batches[0].requested["PRD-1001"]
    assert 옛방식 == 600, "이 검사가 판별하는 지점"


def test_화면과_계산이_같은_원천을_본다():
    batches = [_batch(1, "출고확정", requested=400, shipped=300, cancelled_qty=100)]
    result = analyze({"PRD-1001": 1000}, batches)

    화면_실출고 = result["history"][0]["실출고"]["PRD-1001"]
    계산_잔여 = result["remaining"]["PRD-1001"]

    assert 화면_실출고 == 300
    assert 계산_잔여 == 1000 - 화면_실출고, "화면 숫자와 계산이 어긋나면 사람이 못 믿는다"


def test_진행중인_차수가_있으면_분할을_안_연다():
    batches = [_batch(1, "출고확정", 400, 400), _batch(2, "예약완료", 300, 0)]
    assert split_mode(batches) is False
    assert analyze({"PRD-1001": 1000}, batches)["ok"] is False


def test_잔여가_없으면_다음_차수를_안_연다():
    batches = [_batch(1, "출고확정", 1000, 1000)]
    r = analyze({"PRD-1001": 1000}, batches)
    assert r["ok"] is False and "잔여 없음" in r["reason"]


def test_취소된_차수의_번호는_다시_쓰지_않는다():
    """문서가 이미 '3차' 로 나갔다면 그 번호는 비워둔다."""
    batches = [
        _batch(1, "출고확정", 250, 250),
        Batch(seq=2, state="완전취소", requested={}),
        _batch(3, "출고확정", 250, 250),
    ]
    assert next_sequence(batches) == 4


def test_품목코드가_갈려_있어도_누적이_합쳐진다():
    """같은 물건이 문서마다 다른 코드로 적히는 일이 있다(인증 표기 유무).

    접지 않으면 이미 나간 수량을 못 알아보고 재고 부족으로 막아버린다.
    """
    batches = [Batch(seq=1, state="출고확정",
                     shipments=[ShipmentRecord("PRD-1001-CERT", 250)])]
    fold = lambda c: c.replace("-CERT", "")

    assert remaining({"PRD-1001": 750}, batches, fold) == {"PRD-1001": 500}
    assert remaining({"PRD-1001": 750}, batches) == {"PRD-1001": 750}, "안 접으면 못 알아본다"
