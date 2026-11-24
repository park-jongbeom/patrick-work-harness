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

반복(LANE-LOOP-1-b, 2026-11-24): 「자율 레인 승인: Phase N 까지」면 사이클마다 `card --target N` 으로 카드를 남기고
판정은 반복이 끝난 뒤 한꺼번에 받는다. 원장 끝에서부터 같은 목표의 카드가 이어지는 동안이 「이 반복」이다.
`next --target N` 은 계획 문서(plan_tier 1)의 Phase N 까지 완료 기준·사이클 상한·마지막 카드·커밋 안 된 변경을 보고
계속 / 목표 도달 / 상한 도달 / 멈춤 을 낸다. 판정할 수 없으면 멈춤이다.

사용:
  python3 lane_card.py card [--run] [--target N] [--timeout 600] [--repo .]
  python3 lane_card.py next --target N [--repo .]
  python3 lane_card.py verdict --verdict 승인|경미|심각 [--note "..."] [--session ID] [--repo .]
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
#: Gate A·C 가 남기는 결정 줄 — `- **결정**: 무엇 — 근거: 출처` 또는 `… — 근거 없음`. 근거 표기가 없으면 근거 없음으로 본다.
DECISION = re.compile(r"^[ \t]*[-*][ \t]+\*\*결정\*\*[ \t]*[:：][ \t]*(.+?)[ \t]*$", re.M)
UNSOURCED = re.compile(r"근거\s*없음")
SOURCED = re.compile(r"근거\s*[:：]")
#: 계획 문서의 완료 기준 한 줄 — 상태와 글
CRITERION = re.compile(r"^[ \t]*[-*][ \t]+\[([ xX])\][ \t]*(.*?)[ \t]*$", re.M)
STOP_HINT = "반복을 멈추고 `lane_card.py pending` 으로 이 반복의 카드를 보여 주세요."


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


def ledger_path(repo, name=LEDGER_NAME):
    text = read(os.path.join(repo, ".claude", "harness-answers.yml"))
    m = re.search(r"^archive_path:\s*(.+)$", text, re.M)
    value = m.group(1).split(" #", 1)[0].strip().strip("'\"") if m else ""
    if not value or value.startswith("<"):
        return None
    return os.path.join(value if os.path.isabs(value) else os.path.join(repo, value), name)


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


def loop_cards(entries, target):
    """이 반복의 카드 — 원장 끝에서부터 같은 목표의 카드가 이어지는 동안. 판정이나 다른 목표의 카드가 나오면 끊긴다.

    반복 중에는 판정을 받지 않으므로 이 카드들은 모두 판정이 없다. 판정 없이 같은 목표로 다시 승인하면 앞 반복과
    이어 붙는다 — 사이클 수가 커져 상한에 먼저 닿는 쪽이다.
    """
    run = []
    for e in reversed(entries):
        if target is None or e.get("kind") != "card" or e.get("target") != target:
            break
        run.append(e)
    return run[::-1]


def decisions(content):
    """세션 문서의 결정 줄 → {"sourced": 근거 있는 수, "unsourced": [근거 없음 글…]}. 코드 블록 안은 뺀다."""
    from session_dashboard_parsers import _fence_spans

    spans = _fence_spans(content)
    sourced, unsourced = 0, []
    for m in DECISION.finditer(content):
        if any(a <= m.start() < b for a, b in spans):
            continue
        if SOURCED.search(m.group(1)) and not UNSOURCED.search(m.group(1)):
            sourced += 1
        else:
            unsourced.append(m.group(1))
    return {"sourced": sourced, "unsourced": unsourced}


def plan_path(guard, answers):
    """plan_tier 1 계획 문서의 저장소 상대 경로. 설정이 없거나 저장소 밖이면 None."""
    def value(key):
        m = re.search(rf"^{key}:[ \t]*(.+)$", answers or "", re.M)
        return guard._scalar(m.group(1)) if m else ""

    name = value("single_plan_file")
    if value("plan_tier") != "1" or not name or name.startswith(("<", "${")):
        return None
    if os.path.isabs(name):
        name = os.path.relpath(name, guard.BASE_DIR)
        if name.startswith(".."):
            return None
    return name.strip("/")


def criteria(text):
    """계획 문서 → [(Phase 번호, 체크됨, 기준 글)]. Phase 절은 다음 `##` 머리까지, 코드 블록 안은 뺀다
    (대시보드의 `parse_plan_progress` 와 같은 경계)."""
    from session_dashboard_parsers import _ANY_H2, _PHASE_HEAD, _fence_spans

    spans = _fence_spans(text)

    def live(m):
        return not any(a <= m.start() < b for a, b in spans)

    h2 = [m.start() for m in _ANY_H2.finditer(text) if live(m)]
    out = []
    for head in (m for m in _PHASE_HEAD.finditer(text) if live(m)):
        end = next((p for p in h2 if p > head.start()), len(text))
        out += [(int(head.group(1)), box.group(1) in "xX", box.group(2))
                for box in CRITERION.finditer(text, head.end(), end) if live(box)]
    return out


def criteria_change(before, now):
    """기준 커밋의 계획 문서 → 지금. 반환: (이번에 체크한 기준, 지워지거나 고쳐 쓴 기준) — 「Phase N: 글」 목록.

    고쳐 쓴 기준은 옛 글이 사라진 것으로 잡힌다. 모델이 스스로 체크하는 목표를 모델이 바꾼 것이라 반복을 멈춘다.
    """
    old, new = criteria(before), criteria(now)
    was_checked = {t for _, done, t in old if done}
    now_texts = {t for _, _, t in new}
    checked = [f"Phase {n}: {t}" for n, done, t in new if done and t not in was_checked]
    removed = [f"Phase {n}: {t}" for n, done, t in old if not done and t not in now_texts]
    return checked, removed


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


def build_card(repo, run, timeout, target=None):
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
    scope_flags = []
    try:
        problems, scope_flags, _ = guard.scope_check(plan)
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

    # 반복 카드의 사람 확인거리: 이번 사이클에 체크한 완료 기준(모델이 스스로 채점한 것)과 지운·고쳐 쓴 기준
    checked, removed = [], []
    rel = plan_path(guard, guard.answers_at(base))
    if rel:
        rc, before = guard.git("show", f"{base}:{rel}")
        checked, removed = criteria_change(before if rc == 0 else "", read(os.path.join(repo, rel)))
    if removed:
        flags.append(f"완료 기준이 지워지거나 바뀜 {len(removed)}건")

    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    session_id = parse_current_session(content).get("session_id") or "(세션 ID 없음)"
    flag_triggers = (plan.get("flag_triggers") or "").strip()
    return {
        "kind": "card", "card_id": f"{session_id}@{now}", "ts": now, "session_id": session_id,
        "lane": plan["lane"], "base": base, "head": head, "files": sorted(files), "lines": total_lines,
        "acceptance": [{"cmd": a["cmd"], "rc": a["rc"]} for a in acceptance],
        "scope_problems": scope_problems, "self_debug": mk["self_debug"], "fix_b": mk["fix_b"],
        "dep": mk["dep"], "flags": flags, "verdict": "대기",
        "target": target, "scope_flags": scope_flags,
        "flag_triggers": "" if flag_triggers in ("", "없음") else flag_triggers,
        "decisions": decisions(content), "criteria_checked": checked, "criteria_removed": removed,
    }, acceptance


def loop_lines(card, indent=""):
    """반복 카드에만 붙는 줄 — 표시(걸렸지만 진행한 것), 근거 없음 결정, 체크한·지운 완료 기준. 값이 없으면 줄도 없다."""
    lines = []
    shown = list(card.get("scope_flags") or [])
    if card.get("flag_triggers"):
        shown.append("계획의 표시 트리거 — " + card["flag_triggers"])
    if shown:
        lines.append(f"{indent}- 표시(진행함): " + "; ".join(shown))
    made = card.get("decisions") or {}
    unsourced = made.get("unsourced") or []
    if made.get("sourced") or unsourced:
        lines.append(f"{indent}- 결정 {made.get('sourced', 0) + len(unsourced)}건 · 근거 없음 {len(unsourced)}건")
        lines += [f"{indent}  - 근거 없음: {t}" for t in unsourced]
    for key, label in (("criteria_checked", "이번 사이클에 체크한 완료 기준"), ("criteria_removed", "지워지거나 바뀐 완료 기준")):
        if card.get(key):
            lines.append(f"{indent}- {label} {len(card[key])}건")
            lines += [f"{indent}  - {t}" for t in card[key]]
    return lines


def card_markdown(card, acceptance, earlier_pending, loop=()):
    def rc_text(rc):
        return "재실행 안 함" if rc is None else ("통과" if rc == 0 else f"실패 (rc={rc})")

    target = card.get("target")
    title = "자율 레인" if target is None else f"자율 레인 · 반복 Phase {target} 까지 · 사이클 {len(loop) + 1}"
    lines = [f"### 검토 카드 ({title}) — {card['session_id']}", "",
             f"- 기준 커밋 `{card['base']}` → HEAD `{card['head']}` · 파일 **{len(card['files'])}개** · "
             f"**{card['lines']}줄**"]
    lines += [f"  - `{p}`" for p in card["files"]]
    for a in acceptance:
        lines.append(f"- 수락 명령 `{a['cmd']}` → **{rc_text(a['rc'])}**")
        lines += [f"  > {t}" for t in a.get("tail", [])]
    lines.append("- 범위 가드: " + ("통과" if not card["scope_problems"] else
                                  "위반 — " + "; ".join(card["scope_problems"])))
    lines += loop_lines(card)
    lines.append(f"- self-debug {card['self_debug']}회 · FIX-B {card['fix_b']}건 · DEP {card['dep']}건")
    lines.append("- 깃발: " + ("없음" if not card["flags"] else " / ".join(card["flags"])))
    if earlier_pending:
        lines.append("- 판정 없는 이전 카드: " + ", ".join(e["session_id"] for e in earlier_pending))
    if loop:
        lines.append(f"- 이 반복의 앞 카드 {len(loop)}장: " + ", ".join(e["session_id"] for e in loop))
    lines += ["", f"볼 곳: `git diff {card['base']}`"]
    if target is None:
        lines.append("판정: 「카드 승인」 또는 「지적: 심각|경미 — 내용」으로 답해 주세요.")
    else:
        lines.append(f"판정은 반복이 끝나면 한꺼번에 받습니다 — 다음: `lane_card.py next --target {target}`")
    return "\n".join(lines)


def cmd_card(args):
    path = ledger_path(args.repo)
    if not path:
        print("검토 카드를 남길 곳이 없습니다 — .claude/harness-answers.yml 에 archive_path 가 필요합니다. "
              "자율 레인을 멈추고 사용자에게 알리세요.", file=sys.stderr)
        return 1
    card, acceptance = build_card(args.repo, args.run, args.timeout, args.target)
    entries = read_ledger(path)
    loop = loop_cards(entries, args.target)
    in_loop = {e.get("card_id") for e in loop}
    earlier = [e for e in pending_cards(entries) if e.get("card_id") not in in_loop]
    if earlier:
        card["flags"].append(f"이전 카드 미판정 {len(earlier)}건")
    if args.target is not None:
        card["cycle"] = len(loop) + 1
    append(path, card)
    print(card_markdown(card, acceptance, earlier, loop))
    return 0


def loop_verdict(repo, target, entries):
    """반복을 이을지 — 반환: (판정, 사유, 남은 완료 기준). 판정은 계속·목표 도달·상한 도달·멈춤 중 하나.

    판정할 수 없으면 모두 멈춤이다(계획 문서·Phase·기준·카드가 없거나, 마지막 사이클이 막혔거나, 커밋 안 된 변경).
    설정은 HEAD 의 것을 읽는다 — `.claude/` 는 반복 중 바꿀 수 없는 멈춤 범주다.
    """
    from session_dashboard_parsers import parse_plan_progress

    guard = load_guard(repo)
    answers = guard.answers_at("HEAD")
    try:
        cap = guard.lane_settings(answers)["max_cycles"]
    except guard.Unverifiable as e:
        return "멈춤", f"설정을 읽지 못함 — {e}", []
    rel = plan_path(guard, answers)
    if not rel:
        return "멈춤", "설정에 plan_tier 1 계획 문서(single_plan_file)가 없음 — 목표를 판정할 수 없음", []
    text = read(os.path.join(repo, rel))
    progress = parse_plan_progress(text)
    phases = [p for p in progress.get("phases") or [] if p["num"] <= target]
    if not any(p["num"] == target for p in phases):
        return "멈춤", f"계획 문서 {rel} 에 Phase {target} 이 없음", []
    empty = [str(p["num"]) for p in phases if not p["criteria_total"]]
    if empty:
        return "멈춤", f"완료 기준(체크박스)이 없는 Phase {', '.join(empty)} — 목표를 판정할 수 없음", []

    loop = loop_cards(entries, target)
    if not loop:
        return "멈춤", f"이 반복의 카드가 없음 — Gate E 에서 `card --run --target {target}` 을 먼저", []
    last = loop[-1]
    stuck = []
    if last.get("lane") != "자율":
        stuck.append("레인 판정이 자율이 아님")
    if last.get("scope_problems"):
        stuck.append(f"범위 위반 {len(last['scope_problems'])}건")
    if not last.get("acceptance") or any(a.get("rc") != 0 for a in last["acceptance"]):
        stuck.append("수락 명령 실패 또는 재실행 안 함")
    if last.get("criteria_removed"):
        stuck.append(f"완료 기준 지움·바뀜 {len(last['criteria_removed'])}건")
    if stuck:
        return "멈춤", f"막힘 — {last.get('session_id')}: " + "; ".join(stuck), []

    rc, status = guard.git("status", "--porcelain")
    if rc != 0:
        return "멈춤", "git 상태를 읽지 못함", []
    dirty = [p for p in (line[3:].split(" -> ")[-1].strip('"') for line in status.splitlines() if line.strip())
             if p not in guard.SESSION_DOCS]
    if dirty:
        return "멈춤", f"커밋 안 된 변경 {len(dirty)}개 — " + ", ".join(dirty[:5]), []

    remaining = [f"Phase {n}: {t}" for n, done, t in criteria(text) if n <= target and not done]
    done, total = sum(p["criteria_done"] for p in phases), sum(p["criteria_total"] for p in phases)
    where = f"Phase {target} 까지 완료 기준 {done}/{total} · 사이클 {len(loop)}/{cap}"
    if done == total:
        return "목표 도달", where, []
    if len(loop) >= cap:
        return "상한 도달", where, remaining
    return "계속", where, remaining


def cmd_next(args):
    path = ledger_path(args.repo)
    if not path:
        print("원장 경로가 없습니다 — archive_path 가 필요합니다. 반복을 멈추고 사용자에게 알리세요.", file=sys.stderr)
        return 1
    verdict, reason, remaining = loop_verdict(args.repo, args.target, read_ledger(path))
    lines = [f"반복 판정: {verdict} — {reason}"]
    if remaining:
        lines.append("남은 완료 기준:")
        lines += [f"- {t}" for t in remaining[:10]]
        if len(remaining) > 10:
            lines.append(f"- … 외 {len(remaining) - 10}건")
    if verdict != "계속":
        lines.append(STOP_HINT)
    print("\n".join(lines))
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
    entries = read_ledger(path)
    cards = [e for e in entries if e.get("kind") == "card"]
    pending = pending_cards(entries)
    lines = [f"판정 없는 카드 {len(pending)}건"]
    for e in pending:
        # 반복 카드는 사이클 커밋 뒤에 다음 카드가 그 커밋을 기준으로 삼는다 — 이 사이클의 변경은 거기까지다
        after = cards[cards.index(e) + 1:]
        end = after[0].get("base") if e.get("target") is not None and after \
            and after[0].get("target") == e.get("target") else "HEAD"
        lines.append(f"- **{e.get('session_id')}** ({e.get('ts')}) · 파일 {len(e.get('files') or [])}개 · "
                     f"{e.get('lines', 0)}줄 · 볼 곳 `git diff {e.get('base')}..{end}`")
        if e.get("flags"):
            lines.append("  - 깃발: " + " / ".join(e["flags"]))
        lines += loop_lines(e, "  ")
    if pending:
        lines += ["", "판정: 「모두 승인」 또는 카드마다 「{세션 ID} 지적: 심각|경미 — 내용」 — 기록은 "
                      "`lane_card.py verdict --session {세션 ID} --verdict …`"]
    print("\n".join(lines))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="자율 레인 검토 카드와 원장")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("card", "next", "verdict", "pending"):
        p = sub.add_parser(name)
        p.add_argument("--repo", default=os.environ.get("CLAUDE_PROJECT_DIR") or ".")
        if name == "card":
            p.add_argument("--run", action="store_true", help="수락 명령을 다시 실행해 결과를 싣는다")
            p.add_argument("--timeout", type=int, default=600)
            p.add_argument("--target", type=int, default=None, help="반복의 목표 Phase(「자율 레인 승인: Phase N 까지」)")
        if name == "next":
            p.add_argument("--target", type=int, required=True, help="반복의 목표 Phase")
        if name == "verdict":
            p.add_argument("--verdict", required=True)
            p.add_argument("--note", default="")
            p.add_argument("--session", default="")
    args = parser.parse_args(argv)
    args.repo = os.path.abspath(args.repo)
    return {"card": cmd_card, "next": cmd_next, "verdict": cmd_verdict, "pending": cmd_pending}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
