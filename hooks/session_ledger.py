#!/usr/bin/env python3
"""세션 원장 — Gate E 가 모든 세션의 결과를 한 줄로 남긴다 (2026-10-22).

왜: 하네스를 고칠 근거는 실제 작업의 결과다. 대화 기록(harness_report.py 가 읽는 것)에는 가드의 동작은 남지만,
세션이 무엇을 바꿨는지, 검증이 어땠는지, 사람이 무엇을 바로잡았는지는 남지 않고, 그 기록은 이 PC 에만 있다.
이 스크립트는 세션 문서와 git 에서 결과를 읽어 `<archive_path>/session-ledger.jsonl` 에 한 줄을 덧붙인다
(자율 레인 원장과 같은 폴더, 덧붙이기만 한다). 레인과 상관없이 모든 세션에 쓴다.

스크립트가 읽는 값: 세션 ID, 레인 판정, Gate 진행, R/V/D, 일괄 실행, Gate D 표지(self-debug·FIX-B·DEP),
변경 파일·줄 수(기준 커밋이 주어질 때, 세션 문서·하네스 문서 경로 제외), 엔진 버전, 자율 레인 카드 판정.
모델이 넘기는 값(「모델 기록」으로 표시): 모델 ID, 이번 세션에서 사람이 지적하거나 바로잡은 것.

사용:
  python3 session_ledger.py append [--repo .] [--base <Gate D 의 기준 커밋>] [--model <모델 ID>] [--finding "내용"]...
"""

import argparse
import datetime
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

LEDGER_NAME = "session-ledger.jsonl"
SELF_REPORTED = "모델 기록"


def cell(content, label):
    """대시보드 표의 한 칸(`| 라벨 | 값 |`)."""
    m = re.search(rf"^\|\s*{re.escape(label)}\s*\|\s*([^|\n]*?)\s*\|", content, re.M)
    return m.group(1) if m else ""


def engine_version(repo, manifest_dirs=None):
    """플러그인 매니페스트(이 스크립트와 함께 배포된 것) → 없으면 프로젝트의 harness-answers.yml."""
    root = os.path.dirname(HERE)
    for d in manifest_dirs if manifest_dirs is not None else [root, os.path.join(root, ".claude-plugin")]:
        try:
            with open(os.path.join(d, "plugin.json"), encoding="utf-8") as f:
                version = json.load(f).get("version")
            if version:
                return {"value": version, "source": "plugin.json"}
        except (OSError, ValueError):
            continue
    from lane_card import read

    m = re.search(r'^_engine_version:\s*"?([^"\n]+)"?', read(os.path.join(repo, ".claude", "harness-answers.yml")), re.M)
    return {"value": m.group(1).strip(), "source": "harness-answers.yml"} if m else {"value": None, "source": "모름"}


def lane_card_link(path, session_id):
    from lane_card import read_ledger

    entries = read_ledger(path)
    cards = [e for e in entries if e.get("kind") == "card" and e.get("session_id") == session_id]
    if not cards:
        return None
    card_id = cards[-1].get("card_id")
    verdicts = [e.get("verdict") for e in entries if e.get("kind") == "verdict" and e.get("card_id") == card_id]
    return {"card_id": card_id, "verdict": verdicts[-1] if verdicts else "대기"}


def build_record(repo, base, model, findings):
    from lane_card import load_guard, markers, read
    from report_facts import category, changed_files, changed_lines
    from session_dashboard_parsers import parse_current_session, parse_lane_decision

    content = read(os.path.join(repo, "CURRENT_SESSION.md"))
    guard = load_guard(repo)
    flags = []
    mk = markers(content)
    if mk["self_debug"] is None or mk["fix_b"] is None:
        flags.append("Gate D 표지 없음 (self-debug N회 · FIX-B N건)")
    batch = re.search(r"일괄 실행:\s*(C~E|D~E)", content)
    changed = None
    if base:
        exempt = list(guard.SESSION_DOCS) + guard.doc_paths(read(os.path.join(repo, ".claude", "harness-answers.yml")))
        try:
            files = [(s, p) for s, p in changed_files(repo, base)
                     if not any(p == d or p.startswith(d + "/") for d in exempt)]
            lines = changed_lines(repo, base)
            by_cat = {}
            for _, path in files:
                by_cat[category(path)] = by_cat.get(category(path), 0) + 1
            changed = {"files": len(files), "lines": sum(lines.get(p, 0) for _, p in files),
                       "by_category": dict(sorted(by_cat.items()))}
        except Exception as e:  # git 실패는 숫자 대신 사유로
            flags.append(f"변경 수치를 못 읽음 — {e}")
    else:
        flags.append("기준 커밋 없음 — 변경 수치를 세지 않음")
    session_id = parse_current_session(content).get("session_id") or "(세션 ID 없음)"
    return {
        "kind": "session", "ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "session_id": session_id, "lane": parse_lane_decision(content)["lane"],
        "gate_progress": cell(content, "Gate 진행"), "rvd": cell(content, "R/V/D 분해"),
        "batch": batch.group(1) if batch else None,
        "self_debug": mk["self_debug"], "fix_b": mk["fix_b"], "dep": mk["dep"],
        "base": base or None, "head": guard.git("rev-parse", "--short", "HEAD")[1].strip() or None,
        "changed": changed, "engine_version": engine_version(repo),
        "model": {"value": model or None, "source": SELF_REPORTED},
        "human_findings": {"count": len(findings), "items": findings, "source": SELF_REPORTED},
        "lane_card": None, "flags": flags,
    }


def cmd_append(args):
    from lane_card import append, ledger_path

    path = ledger_path(args.repo, LEDGER_NAME)
    if not path:
        print("세션 원장을 남길 곳이 없습니다 — .claude/harness-answers.yml 에 archive_path 가 필요합니다. "
              "Gate E 는 계속하되 이 사실을 보고하세요.", file=sys.stderr)
        return 1
    record = build_record(args.repo, args.base, args.model, args.finding)
    record["lane_card"] = lane_card_link(ledger_path(args.repo), record["session_id"])
    append(path, record)
    changed = record["changed"]
    print(f"세션 원장 기록: {record['session_id']} · 레인 {record['lane']} · "
          + (f"파일 {changed['files']}·{changed['lines']}줄" if changed else "변경 수치 없음")
          + f" · 사람 지적 {record['human_findings']['count']}건"
          + (f" · 깃발: {' / '.join(record['flags'])}" if record["flags"] else ""))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="세션 원장")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("append")
    p.add_argument("--repo", default=os.environ.get("CLAUDE_PROJECT_DIR") or ".")
    p.add_argument("--base", default="", help="Gate D 사실 블록에 쓴 기준 커밋")
    p.add_argument("--model", default="", help="이 세션을 진행한 모델 ID")
    p.add_argument("--finding", action="append", default=[], help="사람이 지적·정정한 것 한 건(여러 번 쓸 수 있다)")
    args = parser.parse_args(argv)
    args.repo = os.path.abspath(args.repo)
    return cmd_append(args)


if __name__ == "__main__":
    sys.exit(main())
