#!/usr/bin/env python3
"""Gate B 가 질문할 계획인지 판정한다 (2026-11-05).

왜: 질문 10회 중 끝까지 답한 회차는 1회였고, 사용자는 스킵 이유로 시간과 습관을 골랐다. 질문을 되돌리기 어려운
변경으로 좁힌다. 판정을 모델에게 맡기지 않는 것은, 위험 표에 migration 이 있었는데도 모델이 운영 마이그레이션을
「일반」으로 판정했기 때문이다(2026-10-20). 그 변경은 뒤에 운영 기동에 실패했다.

읽는 것: Gate A 블록의 변경 파일 절과 이해 브리핑 「되돌리는 법」뿐이다. 계획 전체를 읽으면 사소 판정 회차까지
걸렸다(과거 12회 재현 측정, 2026-11-05).

걸리지 않는 것: git 으로 되돌릴 수 있는 변경은 넓어도 걸리지 않는다. 그쪽은 Gate D 의 실제 실행이 맡는다.
문서와 시험만 고치는 경로도 뺀다.

출력은 한 줄이고 항상 exit 0 이다 — 판정기가 고장 나서 Gate 를 멈추면 안 된다. 읽지 못하면 「판정 불가」를 내고,
gate-b Step 0 이 같은 기준을 모델이 적용하게 한다.

사용:
  python3 gate_b_trigger.py [CURRENT_SESSION.md 경로]
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PATH_RULES = (
    ("데이터", re.compile(r"(^|/)(migrations?|alembic|flyway|prisma|db/schema|schema)(/|\.)|\.sql$", re.I)),
    ("보안", re.compile(r"(^|/)\.env|(^|/)(auth|security|permissions?|rbac)(/|\.|_|-)", re.I)),
    ("결제", re.compile(r"(^|/)(payments?|billing)(/|\.|_|-)", re.I)),
    ("운영", re.compile(r"(^|/)(deploy|k8s|terraform|helm)(/|$)|\.github/workflows/|(^|/)docker-compose|(^|/)Dockerfile", re.I)),
)
#: 문서·시험은 경로 이름이 같아도 되돌리기 어려운 변경이 아니다(`SECURITY.md`, `tests/auth/`).
IGNORED_PATH = re.compile(r"\.(md|txt|rst)$|(^|/)(docs?|tests?|__tests__|spec|fixtures)/", re.I)
ROLLBACK_WORDS = re.compile(r"마이그레이션|migration|\bDDL\b|ALTER TABLE|DROP TABLE|운영 DB|운영 데이터|백필|backfill|되돌릴 수 없"
                            r"|복구 불가|복구할 수 없|irreversible|되돌리기 어렵|데이터가 남|배포된|이미 나간", re.I)
#: 「되돌릴 수 없는 것은 없다」 — gate-a 가 되돌릴 수 없는 것을 적게 해서 부정하는 문장이 흔하다.
ROLLBACK_DENIAL = re.compile(r"(?:되돌릴 수 없|복구할 수 없|복구 불가)[^.。\n]{0,12}?[은는이가]\s*(?:없|남지 않)"
                             r"|(?:마이그레이션|migration|DDL)[은는이가]?\s*없", re.I)


def _normalized(path):
    path = path.replace("\\", "/")
    path = path[2:] if path.startswith("./") else path
    return re.sub(r":\d.*$", "", path)      # `a.sql:12` 처럼 줄 번호가 붙은 표기


def classify(paths, rollback):
    """변경 파일과 「되돌리는 법」 글 → {"reasons": [종류마다 첫 근거…]}."""
    reasons = []
    paths = [p for p in map(_normalized, paths) if not IGNORED_PATH.search(p)]
    for kind, rule in PATH_RULES:
        hit = next((p for p in paths if rule.search(p)), None)
        if hit:
            reasons.append(f"{kind}: {hit}")
    word = ROLLBACK_WORDS.search(ROLLBACK_DENIAL.sub("", rollback or ""))
    if word:
        reasons.append(f"되돌리는 법: {word.group(0)}")
    return {"reasons": reasons}


def verdict(content):
    """세션 문서 → {"state": 발동|미발동|판정 불가, "reasons": […], "files": 읽은 파일 수}."""
    unreadable = {"state": "판정 불가", "reasons": [], "files": 0}
    try:
        from session_dashboard_parsers import _find_section, _plan_block, _sections, parse_comprehension
        _, body = _find_section(_sections(_plan_block(content or "")), "files")
        files = re.findall(r"`([^`\n]+)`", body)
        rollback = dict(parse_comprehension(content or "")["briefing"]).get("되돌리는 법", "")
    except Exception:
        return unreadable
    reasons = classify(files, rollback)["reasons"]
    if not reasons and not files:       # 목록을 못 읽은 것을 「걸릴 파일 없음」으로 내면 조용히 통과한다
        return unreadable
    return {"state": "발동" if reasons else "미발동", "reasons": reasons, "files": len(files)}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    path = (argv[0] if argv else "") or os.path.join(os.environ.get("CLAUDE_PROJECT_DIR") or ".", "CURRENT_SESSION.md")
    try:
        with open(path, encoding="utf-8") as f:
            result = verdict(f.read())
    except OSError:
        print(f"판정 불가 — 읽지 못함: {path}")
        return 0
    if result["state"] == "발동":
        print("발동 — " + " · ".join(result["reasons"]))
    elif result["state"] == "미발동":
        print(f"미발동 — 변경 파일 {result['files']}개, 해당 없음")
    else:
        print("판정 불가 — 변경 파일 목록을 읽지 못함")
    return 0


if __name__ == "__main__":
    sys.exit(main())
