#!/usr/bin/env python3
"""Gate A 계획을 새 문맥의 검토자가 다시 써 보게 한다 — 시험 운영 (2026-11-10).

왜: 계획을 쓴 모델은 대화 내내 쌓인 맥락으로 자기 계획을 읽어, 글에 적지 않은 전제를 보지 못한다.
google/elephant-goldfish-model 의 이해도 검토자(「먼저 다시 쓰기」)를 하나만 빌려 온다. 대화 기록도 CLAUDE.md 도
없는 내장 Plan 에이전트가 계획 글만 읽고 다시 쓴다. 그 글이 쓴 사람의 의도(이해 브리핑)와 어긋나는 곳이 계획 글의
구멍이다. 그 저장소도 효과를 잰 자료가 없어 시험으로 둔다 — 유지·철회 기준은 DECISION_LOG 2026-11-10.

언제: Gate B 판정기(`gate_b_trigger.py`)가 「발동」이거나, 대시보드 `R/V/D 분해` 줄의 R 이 6 이상인 계획만 검토한다.
판정기가 「판정 불가」면 R 만 본다 — 출력 줄에 그 상태가 그대로 나온다. Gate A 블록에 성공한 검토 기록
(`- **새 문맥 검토**: 지적 …`)이 있으면 다시 돌리지 않는다(`--force` 로 다시 돌린다). 실패 기록은 막지 않는다.

검토자에게 주는 것: 문서의 첫 Gate A 블록(판정기와 같은 블록)의 원문에서 이해 브리핑과 절차 기록 절을 뺀 것이다.
빼는 절은 제목에 SKIPPED_TITLES 의 낱말이 든 `###` 절뿐이다. 이해 브리핑을 주면 검토자가 그것을 옮겨 적을 뿐이다.
입력은 프로젝트 폴더 안의 git 폴더에 쓴다 — 작업 트리에 파일이 생기지 않고 검토자가 권한 확인 없이 읽는다. git 폴더가
프로젝트 폴더 밖이면(worktree·git 아님) 지시문 안에 계획을 그대로 넣는다.

출력 첫 줄: 「발동 — …」「미실행 — …」(조건에 맞지 않음) 또는 「실패 — …」(스크립트가 준비하지 못함). 항상 exit 0 이다
— 이 스크립트가 고장 나도 Gate A 를 멈추지 않는다.

사용:
  python3 fresh_review.py [CURRENT_SESSION.md 경로] [--force]
"""

import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MARKER = "[새 문맥 검토]"
RECORD_LABEL = "**새 문맥 검토**"
INPUT_NAME = "harness-fresh-review.md"
#: 검토자에게 주지 않는 `###` 절 — 쓴 사람의 요약(이해 브리핑)과, 계획 내용이 아니라 절차를 기록한 절.
#: 부분일치라 짧은 낱말은 계획 내용 절까지 뺀다(「OSS」는 「CROSS-ORIGIN」에 걸린다). 이 서버 기록의 Gate A 문서 29개(대부분 시험 프로젝트) 절 제목으로 대 봤다.
SKIPPED_TITLES = ("이해 브리핑", "교훈 조회", "이해도 게이트", "권장 모델", "모델 권장", "범위 점검", "래더", "주장-근거",
                  "OSS 카탈로그", "적합성 점검", "레인 판정", "새 문맥 검토")
#: 대시보드 표의 `| R/V/D 분해 | R=… |` 칸만 읽는다 — 대시보드·세션 원장과 같은 칸이다. 다른 스킬의 양식 인용
#: (`R/V/D 분해: R={R-A 항목 …}`)이 문서 위쪽에 있어도 걸리지 않는다. 이 서버 기록(2026-11-10)의 그 칸은 모두
#: 숫자였다(그 칸이 있는 기록 30개: R=0 27·R=3 5, 6 이상은 없음).
R_SCORE = re.compile(r"R\s*=\s*(\d+)")
#: 성공한 검토 기록. 계획 글이 이 이름을 말하기만 한 것과 실패 기록은 다시 돌리는 것을 막지 않는다(실제 계획으로 돌려 본 재현).
RECORDED = re.compile(r"^[ \t]*[-*][ \t]+\*\*새 문맥 검토\*\*[ \t]*[:：][ \t]*지적[ \t]*\d", re.MULTILINE)

PROMPT = """{marker} 너는 이 계획을 처음 읽는 검토자다. 계획을 쓴 대화는 볼 수 없고, 이 프로젝트를 모른다. 소프트웨어는 안다.

1. {where} 이것이 검토할 계획 전부다. 계획이 말하는 저장소는 `{root}` 다 — 상대 경로는 이 폴더 기준이다. CURRENT_SESSION.md·SESSION_INDEX.md 같은 세션 문서는 열지 않는다 — 계획 글만으로 이해되는지 보는 검토다.
2. 계획이 이름을 댄 저장소 파일은 확인에 필요한 곳만 열어 봐도 된다. 다른 파일을 찾아다니지 않고, 아무것도 고치거나 실행하지 않는다.

먼저 네 말로 다시 쓴다 — 지적보다 먼저:

## 다시 쓴 계획
- **무엇을 바꾸나**: 2~5문장
- **계획에 따르면 지금 시스템은 어떻게 동작하나**: 2~5문장

다시 쓸 수 없는 절이 있으면 그 절이 Blocker 다. 짐작으로 메우지 않는다.

## 지적
중요한 것부터, 한 줄에 하나: `- [Blocker|Major] <계획의 절 이름> — <무엇이 빠졌거나 어긋났나> — <근거: 계획 문장 인용 또는 읽은 파일:줄>`
- Blocker: 다시 쓸 수 없다. 또는 이대로 구현하면 틀리거나 되돌리기 어렵다.
- Major: 구현자가 다르게 이해할 수 있다 — 정의 없이 쓴 이 프로젝트 고유의 용어, 적지 않은 전제나 순서, 「자동으로 처리된다」처럼 어떻게를 말하지 않는 문장, 코드와 다른 사실 주장. 계획 글에 없는 전제를 코드를 읽고서야 알았다면 그것도 지적이다.
일반적인 공학 용어·문체·사소한 것은 적지 않는다. 근거 없는 지적은 적지 않는다. 지적이 없으면 「지적 없음」 한 줄.{inline}"""

HANDLING = """돌아온 답을 처리한다:
1. 「다시 쓴 계획」을 `### 이해 브리핑` 과 대 본다 — 「무엇을 바꾸나」는 「어떻게 동작하나」의 바뀐 뒤와, 「지금 시스템은 어떻게 동작하나」는 「어떻게 동작하나」의 지금·「왜 바꾸나」의 문제와. 대상·순서·동작이 다르게 읽힌 곳만 지적 1건으로 센다(표현 차이는 세지 않는다). 검토자가 잘못 읽었다고 보기 전에, 계획 글이 그렇게 읽히게 쓰였는지 본다. 지시한 두 절 밖에 덧붙은 절(Plan 의 「Critical Files for Implementation」 등)은 무시한다.
2. 지적마다 하나로 정한다. 등급(Blocker·Major)은 바꾸지 않는다.
   - 고침: 계획 글을 고친다 — Step 2 에서 쓴 문서 모두(CURRENT_SESSION.md·계획 문서)에 같게. 이해되지 않았다는 지적은 그 절의 문장을 고친다 — 검토자만을 위한 설명을 덧붙이지 않는다. 고침이 변경 파일이나 「되돌리는 법」을 바꾸면 이해도 게이트 판정을 다시 돌려 그 줄을 바꾸고 범위 점검도 다시 본다.
   - 올림: 사용자가 정할 일이다. `### 리스크 및 대응` 에 행을 더하고(원인 칸 첫머리 「새 문맥 검토:」), 승인을 요청하는 응답에도 적는다.
   - 반박: 확인할 수 있는 근거(`파일:줄`·명령 출력)를 댈 때만. 이해되지 않았다는 지적은 반박하지 않는다. 반박하고 싶다는 것은 근거가 아니다.
3. Gate A 블록의 이해도 게이트 발동 판정 바로 아래에 한 줄을 남긴다: `- {label}: 지적 N · 고침 M(내용 X) · 올림 K · 반박 J`
   「내용」은 고침 가운데 변경 파일·실행 순서·리스크 대응·되돌리는 법 중 하나를 바꾼 수다 — 글을 다듬기만 한 고침은 넣지 않는다.
   검토자를 부르지 못했거나, 오류로 끝났거나, 답이 비었거나, 「다시 쓴 계획」이 없으면 `- {label}: 실패 — <이유>` 로 적는다. 실패를 「지적 0」으로 적지 않는다 — 돌지 않은 검토는 깨끗한 검토가 아니다."""


def r_score(content):
    """대시보드의 `R/V/D 분해` 줄에서 R 점수. 없으면 None."""
    from session_ledger import cell

    m = R_SCORE.match(cell(content or "", "R/V/D 분해"))
    return int(m.group(1)) if m else None


def decide(content, force=False):
    """세션 문서 → (돌릴까, 사유 한 줄)."""
    from gate_b_trigger import verdict
    from session_dashboard_parsers import _plan_block

    if RECORDED.search(_plan_block(content or "")) and not force:
        return False, "이미 검토함 — 계획을 크게 바꿨으면 --force 로 다시 돌린다"
    gate_b, r = verdict(content), r_score(content)
    reasons = []
    if gate_b["state"] == "발동":
        reasons.append("이해도 게이트 발동(" + " · ".join(gate_b["reasons"]) + ")")
    if r is not None and r >= 6:
        reasons.append(f"R={r}")
    if force:
        reasons.append("--force")
    if reasons:
        return True, " · ".join(reasons)
    return False, f"이해도 게이트 {gate_b['state']} · R={'못 읽음' if r is None else r}"


def review_input(content):
    """검토자에게 줄 계획 원문. `###` 절이 없어 이해 브리핑을 뗄 수 없으면 None."""
    from session_dashboard_parsers import parse_gate_documents

    doc = next((d for d in parse_gate_documents(content or "") if d["gate"] == "A"), None)
    if not doc or not any(t for t, _ in doc["sections"]):
        return None
    kept = [(f"### {t}\n{b}" if t else b) for t, b in doc["sections"]
            if not (t and any(s in t for s in SKIPPED_TITLES))]
    return f"## {doc['heading']}\n\n" + "\n\n".join(kept) + "\n"


def _inside(path, root):
    path, root = os.path.normcase(os.path.realpath(path)), os.path.normcase(os.path.realpath(root))
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:              # 윈도에서 드라이브가 다르다
        return False


def locate(session_path):
    """→ (프로젝트 폴더, 입력을 쓸 곳). 쓸 곳은 프로젝트 폴더 안의 git 폴더이고, 그런 곳이 없으면 None(지시문에 넣는다).

    프로젝트 폴더는 CLAUDE_PROJECT_DIR, 없으면 git 최상위 폴더, 그것도 없으면 세션 문서가 있는 폴더다.
    검토자에게 이 폴더를 알려 준다 — 하위 에이전트의 작업 폴더에 기대지 않는다(실제 계획으로 돌려 본 재현)."""
    here = os.path.dirname(os.path.abspath(session_path))
    top = git_dir = None
    try:
        out = subprocess.run(["git", "-C", here, "rev-parse", "--show-toplevel", "--absolute-git-dir"],
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
        lines = out.stdout.strip().splitlines()
        if out.returncode == 0 and len(lines) == 2:
            top, git_dir = lines
    except (OSError, subprocess.SubprocessError):
        pass
    root = os.environ.get("CLAUDE_PROJECT_DIR") or top or here
    target = os.path.join(git_dir, INPUT_NAME) if git_dir and _inside(git_dir, root) else None
    return root, target


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    force = "--force" in argv
    args = [a for a in argv if a != "--force"]
    path = (args[0] if args else "") or os.path.join(os.environ.get("CLAUDE_PROJECT_DIR") or ".", "CURRENT_SESSION.md")
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
        run, why = decide(content, force)
        if not run:
            print(f"미실행 — {why}")
            return 0
        text = review_input(content)
        if text is None:
            print("미실행 — Gate A 블록에 `###` 절이 없어 이해 브리핑을 뗄 수 없다")
            return 0
        root, target = locate(path)
        if target:
            with open(target, "w", encoding="utf-8") as f:
                f.write(text)
    except Exception as e:         # 고장을 미발동과 구별해 남긴다 — 시험 운영 중 고장 횟수를 셀 수 있어야 한다
        print(f"실패 — 준비하지 못함: {type(e).__name__}: {e}")
        print(f"Gate A 블록의 이해도 게이트 발동 판정 아래에 `- {RECORD_LABEL}: 실패 — 스크립트가 준비하지 못함` 한 줄을 남긴다.")
        return 0
    where = (f"`{target.replace(chr(92), '/')}` 를 Read 로 읽는다." if target
             else "검토할 계획은 이 지시 맨 아래 「=====」 두 줄 사이에 있다.")
    inline = "" if target else f"\n\n=====\n{text}=====\n"
    print(f"발동 — {why}")
    # 하위 에이전트는 뒤에서 돌 수 있다 — 그러면 Agent 호출이 곧바로 돌아와, 기다리라고 하지 않으면 검토 없이 승인을 청한다(대조 검증).
    print('Agent 도구를 subagent_type "Plan" 으로 한 번 부른다. prompt 에는 아래 두 「-----」 줄 사이를 그대로 넣는다.')
    print("답을 받아 처리하기 전에는 승인을 요청하지 않는다(STOP 으로 가지 않는다) — 뒤에서 돌면 완료 알림을 기다린다.")
    print("-----")
    print(PROMPT.format(marker=MARKER, where=where, root=root.replace(chr(92), "/"), inline=inline))
    print("-----")
    print(HANDLING.format(label=RECORD_LABEL))
    return 0


if __name__ == "__main__":
    sys.exit(main())
