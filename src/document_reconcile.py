"""담당자가 손으로 고친 문서와 시스템 계산값이 다를 때 무엇을 진실로 볼 것인가.

배경
  패킹리스트를 시스템이 만들어 주지만, 담당자가 실물을 보고 손으로 다듬어
  고객에게 보내는 일이 있다. 그 문서를 다시 시스템에 넣어 "이게 정답이다" 하고
  반영한다. 그런데 문서와 DB 가 다르면?

★ 겪어보니 두 종류였다 — 반대로 다뤄야 한다

  ① 사람의 판단
        DB   4.84   = 단위중량 0.0242 × 200개  (계산값)
        문서  4.8    = 담당자가 반올림해 적음
     둘 다 맞다. 시스템은 계산대로 내고, 사람은 문서에 편의상 줄여 적는다.
     **DB 는 계산값을 지킨다.** 문서의 반올림으로 정밀도를 깎지 않는다.

  ② 표기 손실 (문서 쪽 실수)
        DB   570 X 260 X 195mm
        문서  570 X 260 X 195      ← 단위가 통째로 빠짐
     이건 판단이 아니라 빠뜨린 것이다. 그대로 옮기면 DB 표기가 무너진다.
     실제로 1,386행 중 1행만 단위 없는 값이 되는 일이 있었다.
     **치수가 같으면 손대지 않고, 쓸 때는 단위를 붙인다.**

  ③ 진짜 다른 값
        DB   4.84  /  문서 5.20
     이건 실물이 달랐다는 뜻이다. **문서가 이긴다.** 그게 반영의 목적이다.

어느 경우든 **사람에게 알린다.** 조용히 넘기면 문서를 고칠 기회가 사라진다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


def _decimals(v: float) -> int:
    s = repr(float(v))
    return len(s.split(".")[1]) if "." in s else 0


def is_rounding_of(doc_value: float, db_value: float) -> bool:
    """문서 값이 DB 값을 자릿수만 줄여 적은 것인가.

    여기 도달한 시점에 두 값은 이미 다르다(같으면 앞에서 걸러진다).
    그러니 'DB 를 문서 자릿수로 반올림하면 문서가 되는가' 만 보면 충분하다 —
    문서 쪽 자릿수가 같거나 많으면 반올림해도 DB 그대로라 성립할 수 없다.
    """
    if doc_value is None or db_value is None:
        return False
    return round(float(db_value), _decimals(doc_value)) == float(doc_value)


_UNIT_TAIL = re.compile(r"([A-Za-z]+)\s*$")


def unit_of(dimension: str) -> str:
    """'570 X 260 X 195mm' → 'mm'. 없으면 ''.

    **끝에 붙은** 글자만 본다. 치수 구분자 'X' 도 알파벳이라, 그냥 '글자가 있나'
    로 보면 단위 없는 값까지 단위가 있다고 잘못 판단한다. (실제로 이걸 틀렸다.)
    """
    m = _UNIT_TAIL.search(_dimension_only(dimension))
    return m.group(1) if m else ""


def _dimension_only(v: str) -> str:
    """'570 X 260 X 195mm // 특수포장' → 치수 부분만. '//' 뒤 메모는 발주별 지시라 보존한다."""
    return str(v or "").split("//")[0].strip().rstrip(",;").strip()


def _numbers(v: str) -> tuple[float, ...]:
    return tuple(float(x) for x in re.findall(r"\d+(?:\.\d+)?", str(v or "")))


@dataclass
class Decision:
    apply: bool          # DB 를 문서 값으로 바꿀 것인가
    value: object        # 바꾼다면 무엇으로
    notice: str          # 사람에게 알릴 말 (없으면 '')


def reconcile_weight(doc_value: float | None, db_value: float | None) -> Decision:
    """무게 — 반올림이면 DB 를 지키고, 진짜 다르면 문서를 따른다."""
    if doc_value is None:
        return Decision(False, db_value, "")             # 문서가 비었으면 지우지 않는다
    if db_value is None:
        return Decision(True, doc_value, "")             # 빈칸 채우기
    if float(doc_value) == float(db_value):
        return Decision(False, db_value, "")
    if is_rounding_of(doc_value, db_value):
        return Decision(False, db_value,
                        f"문서 {doc_value} vs 계산값 {db_value} — "
                        "자릿수만 줄인 표기로 보여 계산값을 둡니다")
    return Decision(True, doc_value, "")


def reconcile_dimension(doc_value: str | None, db_value: str | None) -> Decision:
    """박스 규격 — 치수가 같으면 표기 차이로 손대지 않는다. 단위는 지킨다."""
    doc = _dimension_only(doc_value)
    if not doc:
        return Decision(False, db_value, "")

    old = str(db_value or "")
    unit_missing = not unit_of(doc)
    new = doc if not unit_missing else f"{doc}{unit_of(old) or 'mm'}"

    notice = (f"문서에 단위가 없습니다 — '{new}' 로 봅니다") if unit_missing else ""

    same_numbers = _numbers(doc) == _numbers(old)
    db_lost_unit = not unit_of(old)

    if new == _dimension_only(old):
        return Decision(False, db_value, notice)
    if same_numbers and not db_lost_unit:
        # 치수는 같고 표기만 다르다 — 확정된 문서를 흔들지 않는다
        return Decision(False, db_value, notice)

    # '//' 뒤 메모는 발주별 지시라 살린다
    merged = f"{new} // {old.split('//', 1)[1].strip()}" if "//" in old else new
    return Decision(True, merged, notice)
