"""'지우지 않고 표시한다' — 그 상태를 **한 곳에서만** 정의한다.

왜 안 지우나
  패킹리스트에서 카톤을 합치면(111 + 89 → 200) 남는 행이 생긴다. 지우면
  무엇이 있었는지 알 수 없고, 출고 배정과의 연결도 끊긴다. 그래서 수량을 0 으로
  만들고 상태만 표시해 남긴다. 출고 이력도 취소할 때 지우지 않고 표시만 한다.

★ 대신 치르는 값

  읽는 쪽이 **전부** 그 상태를 걸러야 한다. 한 군데라도 빠뜨리면 그 껍데기가
  진짜 행으로 세어진다.

  실제로 그 버그를 만들었다. 문서와 DB 의 행 수를 비교하는 코드에서 껍데기를
  세는 바람에, "구성이 다르다" 며 멀쩡한 발주 건을 통째로 건너뛰었다.
  그 건은 몇 주 동안 '수동 처리 대상' 으로 잘못 분류돼 있었다.

  더 나빴던 건, **같은 문제를 이미 옆 함수에서 고쳐놨다는 것**이다.
  그 함수 주석에 이 발주번호가 적혀 있었다. 새로 만든 함수만 그 규칙을 안 따랐다.

  ⇒ 걸러야 할 상태를 **여기서만** 정의하고, 읽는 쪽은 전부 여기를 본다.
     SQL 조각도 여기서 만든다. 이름을 바꾸면 양쪽이 같이 따라간다.
"""
from __future__ import annotations

# 만드는 쪽과 읽는 쪽이 같은 글자를 쓰게 한다
NORMAL = "정상"
CANCELLED = "취소"
MERGE_LEFTOVER = "정정잉여"      # 카톤을 합칠 때 남은 수량 0 껍데기
MANUAL_EDIT = "수기수정"

# 문서·집계·출고에서 빼야 하는 상태. 여기만 고치면 SQL 도 따라 바뀐다.
EXCLUDED: tuple[str, ...] = (CANCELLED, MERGE_LEFTOVER)

# 상태가 비어 있으면 '정상' 으로 본다 — 옛 행에는 NULL 이 들어 있다
DEFAULT = NORMAL


def is_live(status: str | None) -> bool:
    """실제로 나가는 물건의 행인가."""
    return (status or DEFAULT) not in EXCLUDED


def live_rows(rows, key="행상태"):
    """행 목록에서 살아 있는 것만. dict 든 객체든 받는다."""
    def _get(r):
        if isinstance(r, dict):
            return r.get(key)
        return getattr(r, key, None)
    return [r for r in rows if is_live(_get(r))]


def sql_live(column: str = '"행상태"') -> str:
    """SQL WHERE 절 조각. 파이썬 쪽 규칙과 갈라지지 않게 여기서 만든다.

    >>> sql_live()
    'COALESCE("행상태",\\'정상\\') NOT IN (\\'취소\\',\\'정정잉여\\')'
    """
    목록 = ",".join(f"'{s}'" for s in EXCLUDED)
    return f"COALESCE({column},'{DEFAULT}') NOT IN ({목록})"
