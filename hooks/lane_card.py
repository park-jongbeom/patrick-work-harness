#!/usr/bin/env python3
"""자율 레인 검토 카드와 원장 (S8a, 2026-10-22).

자율 레인은 사람 정지 없이 구현·검증하고, 사람은 Gate E 에서 이 카드 한 장을 확인한다
(gate-e §0). 카드는 모델의 보고가 아니라 스크립트가 센 사실로 채운다 — 수락 명령은 다시 돌리고,
변경은 report_facts 로, 범위는 lane-scope-guard 와 같은 함수로 본다.

원장은 `<archive_path>/lane-ledger.jsonl` 에 한 줄씩 **덧붙이기만** 한다(고쳐 쓰지 않는다).
  - card    : 카드를 만들 때. 판정 「대기」.
  - verdict : 사람이 카드에 답한 뒤. 승인 · 경미 · 심각.
`pending` 은 판정이 아직 없는 카드를 보여 준다. 자율 레인의 중단 규칙(DECISION_LOG 사전 등록)이
이 원장을 입력으로 쓴다. archive_path 는 레인 범위 가드의 하네스 문서 예외라 원장을 써도 범위
위반이 아니다.

사용:
  python3 lane_card.py card [--run] [--timeout 600] [--repo .]
  python3 lane_card.py verdict --verdict 승인|경미|심각 [--note "..."] [--repo .]
  python3 lane_card.py pending [--repo .]
"""

import argparse
import datetime
import importlib.util
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

VERDICTS = ("승인", "경미", "심각")
LEDGER_NAME = "lane-ledger.jsonl"


def load_guard(repo):
    spec = importlib.util.spec_from_file_location("lane_scope_guard", os.path.join(HERE, "lane-scope-guard.py"))
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    guard.BASE_DIR = repo
    return guard


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def ledger_path(repo):
    text = read(os.path.join(repo, ".claude", "harness-answers.yml"))
    m = re.search(r"^archive_path:\s*(.+)$", text, re.M)
    value = m.group(1).split(" #", 1)[0].strip().strip("'\"") if m else ""
    if not value or value.startswith("<"):
        return None
    return os.path.join(value if os.path.isabs(value) else os.path.join(repo, value), LEDGER_NAME)


def read_ledger(path):
    entries = []
    for line in read(path).splitlines():
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue
    return entries


def pending_cards(entries):
    judged = {e.get("card_id") for e in entries if e.get("kind") == "verdict"}
    return [e for e in entries if e.get("kind") == "card" and e.get("card_id") not in judged]


def append(path, entry):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def markers(content):
    """Gate D 블록의 오류 표지. 없으면 None."""
    from session_dashboard_parsers import _gate_block

    block = _gate_block(content, "D")[1]
    found = {}
    for key, rx in (("self_debug", r"self-debug\s*(\d+)"), ("fix_b", r"FIX-B\s*(\d+)\s*건"),
                    ("dep", r"DEP\s*(\d+)\s*건")):
        m = re.search(rx, block)
        found[key] = int(m.group(1)) if m else None
    return found


def run_acceptance(repo, commands, timeout):
    results = []
    for cmd in commands:
        try:
            proc = subprocess.run(cmd, shell=True, cwd=repo, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=timeout)
            tail = (proc.stdout + proc.stderr).strip().splitlines()[-3:]
            results.append({"cmd": cmd, "rc": proc.returncode, "tail": tail})
        except subprocess.TimeoutExpired:
            results.append({"cmd": cmd, "rc": "timeout", "tail": []})
    return results


def build_card(repo, run, timeout):
    from report_facts import category, changed_files, changed_lines
    from session_dashboard_parsers import parse_current_session, parse_lane_decision

    guard = load_guard(repo)
    content = read(os.path.join(repo, "CURRENT_SESSION.md"))
    plan = parse_lane_decision(content)
    base = plan["base_commit"] or "HEAD"
    head = guard.git("rev-parse", "--short", "HEAD")[1].strip()
    flags = []

    if plan["lane"] != "자율":
        flags.append("레인 판정을 자율로 읽지 못함 — " + "; ".join(plan["reasons"]))
    try:
        problems, _ = guard.scope_violations(plan)
    except Exception as e:
        problems = [f"확인 불가 — {e}"]
    scope_problems = [p for p in problems if not p.startswith("레인 판정을 자율로 읽지 못함")]
    if scope_problems:
        flags.append(f"범위 위반 {len(scope_problems)}건")

    exempt = list(guard.SESSION_DOCS) + guard.doc_paths(guard.answers_at(base))
    try:
        changes = [(s, p) for s, p in changed_files(repo, base)
                   if not any(p == d or p.startswith(d + "/") for d in exempt)]
        files = [p for s, p in changes]
        lines = changed_lines(repo, base)
        added_tests = [p for s, p in changes if s == "A" and category(p) == "tests"]
    except Exception as e:
        files, lines, added_tests = [], {}, []
        flags.append(f"변경 목록을 못 읽음 — {e}")
    total_lines = sum(lines.get(p, 0) for p in files)

    if run:
        acceptance = run_acceptance(repo, plan["acceptance"], timeout)
        failed = [a["cmd"] for a in acceptance if a["rc"] != 0]
        if failed:
            flags.append(f"수락 명령 실패 {len(failed)}건")
    else:
        acceptance = [{"cmd": c, "rc": None, "tail": []} for c in plan["acceptance"]]
        flags.append("수락 명령 재실행 안 함")

    mk = markers(content)
    if mk["self_debug"] is None or mk["fix_b"] is None:
        flags.append("Gate D 표지 없음 (self-debug N회 · FIX-B N건) — error-topics 가드가 읽지 못한다")
    if (mk["self_debug"] or 0) >= 1:
        flags.append(f"self-debug {mk['self_debug']}회")
    if (mk["fix_b"] or 0) >= 1 or (mk["dep"] or 0) >= 1:
        flags.append(f"FIX-B {mk['fix_b'] or 0}건 · DEP {mk['dep'] or 0}건")
    if not added_tests:
        flags.append("새 시험 없음")
    try:
        max_lines = guard.lane_settings(guard.answers_at(base)).get("max_lines", 200)
    except Exception:
        max_lines = 200
    if total_lines > max_lines:
        flags.append(f"계획 줄 수 초과 — {total_lines}줄 > {max_lines}줄")

    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    session_id = parse_current_session(content).get("session_id") or "(세션 ID 없음)"
    return {
        "kind": "card", "card_id": f"{session_id}@{now}", "ts": now, "session_id": session_id,
        "lane": plan["lane"], "base": base, "head": head, "files": sorted(files), "lines": total_lines,
        "acceptance": [{"cmd": a["cmd"], "rc": a["rc"]} for a in acceptance],
        "scope_problems": scope_problems, "self_debug": mk["self_debug"], "fix_b": mk["fix_b"],
        "dep": mk["dep"], "flags": flags, "verdict": "대기",
    }, acceptance


def card_markdown(card, acceptance, earlier_pending):
    def rc_text(rc):
        return "재실행 안 함" if rc is None else ("통과" if rc == 0 else f"실패 (rc={rc})")

    lines = [f"### 검토 카드 (자율 레인) — {card['session_id']}", "",
             f"- 기준 커밋 `{card['base']}` → HEAD `{card['head']}` · 파일 **{len(card['files'])}개** · "
             f"**{card['lines']}줄**"]
    lines += [f"  - `{p}`" for p in card["files"]]
    for a in acceptance:
        lines.append(f"- 수락 명령 `{a['cmd']}` → **{rc_text(a['rc'])}**")
        lines += [f"  > {t}" for t in a.get("tail", [])]
    lines.append("- 범위 가드: " + ("통과" if not card["scope_problems"] else
                                  "위반 — " + "; ".join(card["scope_problems"])))
    lines.append(f"- self-debug {card['self_debug']}회 · FIX-B {card['fix_b']}건 · DEP {card['dep']}건")
    lines.append("- 깃발: " + ("없음" if not card["flags"] else " / ".join(card["flags"])))
    if earlier_pending:
        lines.append("- 판정 없는 이전 카드: " + ", ".join(e["session_id"] for e in earlier_pending))
    lines += ["", f"볼 곳: `git diff {card['base']}`",
              "판정: 「카드 승인」 또는 「지적: 심각|경미 — 내용」으로 답해 주세요."]
    return "\n".join(lines)


def cmd_card(args):
    path = ledger_path(args.repo)
    if not path:
        print("검토 카드를 남길 곳이 없습니다 — .claude/harness-answers.yml 에 archive_path 가 필요합니다. "
              "자율 레인을 멈추고 사용자에게 알리세요.", file=sys.stderr)
        return 1
    card, acceptance = build_card(args.repo, args.run, args.timeout)
    earlier = pending_cards(read_ledger(path))
    if earlier:
        card["flags"].append(f"이전 카드 미판정 {len(earlier)}건")
    append(path, card)
    print(card_markdown(card, acceptance, earlier))
    return 0


def cmd_verdict(args):
    path = ledger_path(args.repo)
    if args.verdict not in VERDICTS:
        print(f"판정은 {', '.join(VERDICTS)} 중 하나입니다: {args.verdict}", file=sys.stderr)
        return 2
    if not path:
        print("원장 경로가 없습니다 — archive_path 가 필요합니다.", file=sys.stderr)
        return 1
    from session_dashboard_parsers import parse_current_session

    session_id = args.session or parse_current_session(
        read(os.path.join(args.repo, "CURRENT_SESSION.md"))).get("session_id")
    cards = [e for e in pending_cards(read_ledger(path)) if e.get("session_id") == session_id]
    if not cards:
        print(f"판정할 카드가 없습니다 (세션 {session_id}) — 먼저 `lane_card.py card` 로 카드를 만드세요.",
              file=sys.stderr)
        return 1
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    append(path, {"kind": "verdict", "ts": now, "card_id": cards[-1]["card_id"], "session_id": session_id,
                  "verdict": args.verdict, "note": args.note or ""})
    print(f"판정 기록: {session_id} — {args.verdict}" + (f" ({args.note})" if args.note else ""))
    return 0


def cmd_pending(args):
    path = ledger_path(args.repo)
    if not path:
        print("원장 경로가 없습니다 — archive_path 가 필요합니다.", file=sys.stderr)
        return 1
    pending = pending_cards(read_ledger(path))
    print(f"판정 없는 카드 {len(pending)}건" + "".join(f"\n- {e['session_id']} ({e['ts']})" for e in pending))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="자율 레인 검토 카드와 원장")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("card", "verdict", "pending"):
        p = sub.add_parser(name)
        p.add_argument("--repo", default=os.environ.get("CLAUDE_PROJECT_DIR") or ".")
        if name == "card":
            p.add_argument("--run", action="store_true", help="수락 명령을 다시 실행해 결과를 싣는다")
            p.add_argument("--timeout", type=int, default=600)
        if name == "verdict":
            p.add_argument("--verdict", required=True)
            p.add_argument("--note", default="")
            p.add_argument("--session", default="")
    args = parser.parse_args(argv)
    args.repo = os.path.abspath(args.repo)
    return {"card": cmd_card, "verdict": cmd_verdict, "pending": cmd_pending}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
