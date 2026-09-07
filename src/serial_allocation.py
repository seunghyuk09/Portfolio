"""시리얼 번호 재고를 '범위' 로 다루는 배정 로직.

왜 범위인가
  제품 하나하나에 S/N 이 붙지만, 100개를 출고할 때 100줄을 적지 않는다.
  패킹리스트에는 `SN0001 ~ SN0100` 처럼 **연속 범위**로 적는다. 세관·고객이
  그렇게 읽고, 행이 100줄이 되면 문서가 못 쓰게 된다.

  그래서 재고도 범위로 들고 있어야 한다. 낱개로 들고 있다가 출고할 때 묶으면
  '어디까지가 한 묶음이었나' 를 잃는다.

여기서 어려운 것
  출고를 거듭하면 범위가 조각난다. 1~100 에서 41~70 을 떼가면 1~40 과 71~100 이
  남는다. 이런 조각이 쌓이면 다음 출고가 `1~40, 71~100, 151~180` 처럼 되고,
  패킹리스트가 지저분해진다.

  → 조각을 **도로 합치고**(인접하면), 요청 수량을 **가장 적은 조각 수**로 채운다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace

# S/N 형식: 영문 접두 + 숫자 (예: SN0001, ABC12345)
#   접두가 다르면 다른 계열이라 절대 이어 붙이지 않는다.
_SN = re.compile(r"^([A-Za-z]*)(\d+)$")


def parse(sn: str) -> tuple[str, int, int]:
    """'SN0042' → ('SN', 42, 4).  마지막은 자릿수 — 되돌릴 때 0 채움에 쓴다."""
    m = _SN.match(sn.strip())
    if not m:
        raise ValueError(f"S/N 형식이 아닙니다: {sn!r}")
    prefix, digits = m.group(1), m.group(2)
    return prefix, int(digits), len(digits)


def format_sn(prefix: str, number: int, width: int) -> str:
    return f"{prefix}{number:0{width}d}"


@dataclass(frozen=True)
class SerialRange:
    """재고 한 조각. start~end 는 양끝 포함이다.

    lot 은 생산 로트. 같은 제품이라도 로트가 다르면 **합치지 않는다** —
    번호는 이어져도 물건이 다르고, 패킹리스트에서 로트별로 구분해 보여줘야 한다.
    """
    prefix: str
    start: int
    end: int
    width: int
    lot: str

    @property
    def qty(self) -> int:
        return self.end - self.start + 1

    @property
    def label(self) -> str:
        return f"{format_sn(self.prefix, self.start, self.width)} ~ {format_sn(self.prefix, self.end, self.width)}"

    def take(self, n: int) -> tuple["SerialRange", "SerialRange | None"]:
        """앞에서 n 개를 떼어낸다. (떼어낸 것, 남은 것)"""
        if not 0 < n <= self.qty:
            raise ValueError(f"{self.qty}개 중 {n}개는 못 뗍니다")
        taken = replace(self, end=self.start + n - 1)
        if n == self.qty:
            return taken, None
        return taken, replace(self, start=self.start + n)


def merge(ranges: list[SerialRange]) -> list[SerialRange]:
    """맞닿은 조각을 도로 합친다.

    출고를 취소하면 떼어갔던 번호가 재고로 돌아온다. 그때 합쳐두지 않으면
    조각이 계속 늘어난다. 접두·로트가 같고 번호가 이어질 때만 합친다.
    """
    if not ranges:
        return []
    ordered = sorted(ranges, key=lambda r: (r.prefix, r.lot, r.start))
    out = [ordered[0]]
    for cur in ordered[1:]:
        last = out[-1]
        이어짐 = (cur.prefix == last.prefix
                and cur.lot == last.lot
                and cur.start == last.end + 1)
        if 이어짐:
            out[-1] = replace(last, end=cur.end)
        else:
            out.append(cur)
    return out


def allocate(stock: list[SerialRange], qty: int) -> tuple[list[SerialRange], list[SerialRange]]:
    """재고에서 qty 개를 배정한다. (배정된 조각들, 남은 재고)

    **큰 조각부터** 쓴다. 작은 것부터 쓰면 자투리가 계속 남아 조각이 늘고,
    패킹리스트 행도 늘어난다. 한 조각으로 끝낼 수 있으면 한 줄로 끝난다.

    같은 크기면 번호가 작은 쪽(=오래된 재고)부터 — 선입선출.
    """
    if qty <= 0:
        raise ValueError("배정 수량은 1 이상이어야 합니다")
    available = sum(r.qty for r in stock)
    if available < qty:
        raise ValueError(f"재고 부족: {available}개 있는데 {qty}개 요청")

    후보 = sorted(stock, key=lambda r: (-r.qty, r.prefix, r.start))
    배정: list[SerialRange] = []
    남은재고: list[SerialRange] = []
    필요 = qty

    for r in 후보:
        if 필요 == 0:
            남은재고.append(r)
        elif r.qty <= 필요:
            배정.append(r)
            필요 -= r.qty
        else:
            taken, rest = r.take(필요)
            배정.append(taken)
            if rest is not None:
                남은재고.append(rest)
            필요 = 0

    # 문서에 나가는 순서는 번호순이라야 사람이 읽는다.
    배정.sort(key=lambda r: (r.prefix, r.start))
    return 배정, merge(남은재고)


def release(stock: list[SerialRange], returned: list[SerialRange]) -> list[SerialRange]:
    """출고 취소 등으로 되돌아온 조각을 재고에 합친다."""
    return merge(list(stock) + list(returned))
