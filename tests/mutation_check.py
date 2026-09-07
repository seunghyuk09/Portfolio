"""회귀 테스트가 **진짜 잡는지** 검사한다 — 돌연변이(mutation) 하네스.

왜 만들었나
  테스트가 초록불이라고 안심하면 안 된다. 아무것도 검사하지 않는 테스트도
  초록불이다. 실제로 겪은 것들:

    · 정규식이 깨져 아무것도 매치하지 않는데 통과하고 있었다
    · 문자열만 보는 검사라 `if False and ...` 로 죽여도 통과했다
    · 같은 단언을 네 번 복사해 놓고 "검사 21개" 라고 세고 있었다

  그래서 **코드를 일부러 고장 내고** 테스트를 돌린다. 빨간불이 안 뜨면
  그 테스트는 장식이다.

읽는 법
  잡음   고장을 냈더니 테스트가 빨개졌다 — 좋다
  놓침   고장을 냈는데도 초록불이다 — 그 테스트는 아무것도 안 지키고 있다
  무효   테스트가 아예 못 돌았다(구문 오류 등) — 시험 자체가 성립 안 함

  ★ '무효' 를 '잡음' 으로 세면 안 된다. 예전에 종료코드만 보고 판정했다가
    ImportError 로 죽은 것을 '잡았다' 고 착각한 적이 있다. 그래서 여기서는
    **테스트가 끝까지 돌았다는 증거**(요약 줄)를 먼저 확인한다.

실행
    python tests/mutation_check.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (설명, 대상 파일, 바꿀 것, 바꿔 넣을 것)
#   고장은 '실수로 그렇게 짤 법한 것' 이라야 의미가 있다.
MUTATIONS = [
    ("잔여를 '걸어둔 수량' 으로 되돌린다 (옛 버그)",
     "src/split_shipment.py",
     "for code, qty in b.shipped().items():",
     "for code, qty in b.requested.items():"),

    ("취소된 출고를 계산에 포함시킨다",
     "src/split_shipment.py",
     "            if s.cancelled:\n                continue\n",
     ""),

    ("취소된 차수를 계산에 포함시킨다",
     "src/split_shipment.py",
     "return [b for b in batches if b.state not in CANCELLED_STATES]",
     "return list(batches)"),

    ("작은 조각부터 써서 행이 늘어나게 한다",
     "src/serial_allocation.py",
     "후보 = sorted(stock, key=lambda r: (-r.qty, r.prefix, r.start))",
     "후보 = sorted(stock, key=lambda r: (r.qty, r.prefix, r.start))"),

    ("로트가 달라도 조각을 합친다",
     "src/serial_allocation.py",
     "and cur.lot == last.lot\n",
     ""),

    ("반올림도 문서 값으로 덮어쓴다",
     "src/document_reconcile.py",
     "    if is_rounding_of(doc_value, db_value):",
     "    if False:"),

    ("단위 판정을 '아무 글자나' 로 되돌린다 ('X' 를 단위로 오인)",
     "src/document_reconcile.py",
     '_UNIT_TAIL = re.compile(r"([A-Za-z]+)\\s*$")',
     '_UNIT_TAIL = re.compile(r"([A-Za-z]+)")'),

    ("껍데기 행을 걸러내지 않는다",
     "src/row_status.py",
     "EXCLUDED: tuple[str, ...] = (CANCELLED, MERGE_LEFTOVER)",
     "EXCLUDED: tuple[str, ...] = ()"),
]


def run_tests() -> tuple[bool, bool]:
    """(테스트가 끝까지 돌았나, 통과했나)"""
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "--no-header"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (r.stdout or "") + (r.stderr or "")
    # pytest 가 결과 요약을 냈다는 것 = 수집·실행이 됐다는 증거
    돌았나 = bool(re.search(r"\d+ (passed|failed)", out))
    return 돌았나, r.returncode == 0


def main() -> int:
    print("돌연변이 검사 — 코드를 일부러 고장 내고 회귀가 잡는지 본다\n")

    돌았나, 통과 = run_tests()
    if not (돌았나 and 통과):
        print("  멀쩡한 코드에서 이미 실패합니다. 먼저 고치세요.")
        return 1
    print("  기준: 멀쩡한 코드는 전부 통과 ✓\n")

    잡음 = 놓침 = 무효 = 0
    for 설명, 파일, old, new in MUTATIONS:
        path = ROOT / 파일
        원본 = path.read_text(encoding="utf-8")

        if 원본.count(old) != 1:
            print(f"  [무효  ] {설명}\n           대상 {원본.count(old)}곳 — 고장을 못 냈다")
            무효 += 1
            continue

        path.write_text(원본.replace(old, new, 1), encoding="utf-8")
        try:
            돌았나, 통과 = run_tests()
        finally:
            path.write_text(원본, encoding="utf-8")   # 무슨 일이 있어도 되돌린다

        if not 돌았나:
            print(f"  [무효  ] {설명}\n           테스트가 못 돌았다 — 시험 성립 안 함")
            무효 += 1
        elif not 통과:
            print(f"  [잡음  ] {설명}")
            잡음 += 1
        else:
            print(f"  [놓침★ ] {설명}\n           고장을 냈는데 초록불 — 이 부분은 아무도 안 지킨다")
            놓침 += 1

    print(f"\n  고장 {len(MUTATIONS)}개 — 잡음 {잡음} · 놓침 {놓침} · 무효 {무효}")
    if 놓침:
        print("  놓친 항목에 회귀를 추가하세요.")
    return 1 if (놓침 or 무효) else 0


if __name__ == "__main__":
    raise SystemExit(main())
