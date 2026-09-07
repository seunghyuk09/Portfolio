"""분할출고 — 주문을 여러 차수로 나눠 보낼 때 '잔여' 를 얼마로 볼 것인가.

상황
  1,000개 주문을 400 → 600 으로 나눠 보낸다. 2차 파일을 올리면 시스템이
  "이전에 400 나갔으니 잔여 600" 이라고 알려주고, 그만큼 배정하게 한다.

★ 여기서 실제로 겪은 문제

  잔여를 이렇게 셌다.

      잔여 = 주문 − Σ 이전 차수에 **걸어둔** 수량(요청수량)

  그런데 '걸어둔 수량' 은 출고를 취소해도 줄지 않는다. 화면에는 출고 이력에서
  가져온 '실출고' 를 보여주면서, 계산만 다른 값을 쓰고 있었다.

      화면    1차 실출고 300
      계산    1,000 − 400 = 600      ← 100개가 붕 뜬다

  처음엔 "일어날 수 없다" 고 결론냈다. 출고확정을 취소하면 그 차수의 상태가
  '확정' 이 아니게 되고, 그러면 분할 계산 자체가 꺼지기 때문이다.

  **틀렸다.** 되돌아오는 길이 있었다.

      취소 → 배정 축소 → 문서 재생성 → 다시 확정

  다시 확정하면 상태가 '확정' 으로 돌아와 분할 계산이 살아난다. 그런데
  '걸어둔 수량' 은 그 사이 아무도 줄이지 않는다. **요청수량은 그대로, 실출고만
  줄어든 채** 잔여가 계산된다.

  이 사이클은 화면의 버튼 하나로 시작된다. 실제 운영 데이터에서 그 경로로
  취소된 출고 이력이 200행 넘게 있었다.

  ⇒ 잔여도 **실제로 나간 것**에서 센다. 화면과 계산이 같은 원천을 본다.

교훈으로 남길 것
  "지금 틀린 데이터가 있는가" 와 "그렇게 될 경로가 있는가" 는 다른 질문이다.
  당시 실제 데이터는 전부 일치했다. 못 일어나는 게 아니라 아직 안 일어난 것이었다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# 계산에서 빼야 하는 출고요청 상태 — 취소 계열
CANCELLED_STATES = frozenset({"취소", "완전취소", "출고취소"})
CONFIRMED = "출고확정"


@dataclass
class ShipmentRecord:
    """실제로 나간 한 건. 취소하면 지우지 않고 표시만 한다."""
    item_code: str
    qty: int
    cancelled: bool = False


@dataclass
class Batch:
    """한 차수(1차, 2차 …)."""
    seq: int
    state: str
    requested: dict[str, int] = field(default_factory=dict)   # 걸어둔 수량
    shipments: list[ShipmentRecord] = field(default_factory=list)

    def shipped(self) -> dict[str, int]:
        """실제로 나간 수량. 취소분은 뺀다 — 이게 '나갔다' 의 진실이다."""
        out: dict[str, int] = {}
        for s in self.shipments:
            if s.cancelled:
                continue
            out[s.item_code] = out.get(s.item_code, 0) + s.qty
        return out


def active_batches(batches: list[Batch]) -> list[Batch]:
    """취소 계열은 아예 없던 것으로 본다."""
    return [b for b in batches if b.state not in CANCELLED_STATES]


def split_mode(batches: list[Batch]) -> bool:
    """분할 계산을 켤 수 있는가.

    이전 차수가 하나라도 '확정' 이 아니면 끈다 — 아직 진행 중인 차수가 있는데
    다음 차수를 만들면 같은 재고를 두 번 잡는다.
    """
    active = active_batches(batches)
    return bool(active) and all(b.state == CONFIRMED for b in active)


def shipped_total(batches: list[Batch], fold=lambda c: c) -> dict[str, int]:
    """이전 차수들에서 **실제로 나간** 누적 수량.

    fold 는 품목코드를 대표코드로 접는 함수. 같은 물건이 문서마다 다른 코드로
    적히는 일이 있어서(인증 표기가 붙거나 빠지거나), 접지 않으면 이미 나간
    수량을 못 알아보고 '재고 부족' 으로 막아버린다.
    """
    누적: dict[str, int] = {}
    for b in active_batches(batches):
        for code, qty in b.shipped().items():
            k = fold(code)
            누적[k] = 누적.get(k, 0) + qty
    return 누적


def remaining(order_qty: dict[str, int], batches: list[Batch],
              fold=lambda c: c) -> dict[str, int]:
    """품목별 잔여 = 주문 − 실제로 나간 것."""
    누적 = shipped_total(batches, fold)
    return {code: max(0, qty - 누적.get(fold(code), 0))
            for code, qty in order_qty.items()}


def next_sequence(batches: list[Batch]) -> int:
    """다음 차수 번호. 취소된 차수의 번호는 다시 쓰지 않는다 — 문서에 남아 있다."""
    used = [b.seq for b in batches if b.seq]
    return (max(used) + 1) if used else 1


def analyze(order_qty: dict[str, int], batches: list[Batch],
            fold=lambda c: c) -> dict:
    """다음 차수를 만들 수 있는지, 얼마나 남았는지 한 번에 답한다."""
    if not split_mode(batches):
        미완료 = [b.seq for b in active_batches(batches) if b.state != CONFIRMED]
        return {
            "ok": False,
            "reason": ("이전 차수가 아직 진행 중입니다: "
                       f"{미완료}") if 미완료 else "이전 차수가 없습니다",
            "remaining": {},
        }

    남은 = remaining(order_qty, batches, fold)
    if not any(v > 0 for v in 남은.values()):
        return {"ok": False, "reason": "잔여 없음 — 주문 수량을 모두 출고했습니다",
                "remaining": 남은}

    return {
        "ok": True,
        "next_seq": next_sequence(batches),
        "remaining": 남은,
        # 화면에 그대로 띄우는 이력. 계산과 **같은 원천**이라야 사람이 믿는다.
        "history": [
            {"차수": b.seq, "상태": b.state,
             "걸어둔수량": dict(b.requested), "실출고": b.shipped()}
            for b in active_batches(batches)
        ],
    }
