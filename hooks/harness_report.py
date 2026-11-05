#!/usr/bin/env python3
"""하네스 사용 보고서 — 대화 기록에서 하네스가 실제로 어떻게 동작했는지 뽑는다 (2026-10-22).

왜: 하네스를 고칠 근거는 실제 작업에서 나와야 하는데, 가드가 언제 무엇을 했고 사용자가 어떻게 응답했는지를
세는 도구가 없었다. 가드의 자체 카운터는 임시 폴더라 재부팅하면 사라진다. Claude Code 의 대화 기록에는 훅
실행이 남는다(명령·출력·종료 코드·소요 시간). 이 스크립트는 그것을 세션 표로 바꾸고, DECISION_LOG 의 대기
예측이 확인 시점까지 얼마나 왔는지 보여 준다. 기록을 읽기만 한다 — 훅으로 배선하지 않는다.

읽는 기록 형식(Claude Code 2.1.307 에서 확인):
  - 훅 실행: `attachment` 줄 — hook_success(stdout·command·durationMs·toolUseID), hook_system_message(알림),
    hook_additional_context, hook_blocking_error, hook_non_blocking_error
  - 훅의 exit 2 거부: 도구 결과 「PreToolUse:X hook error: [명령]: …」
  - Stop 훅 묶음: system `stop_hook_summary`(hookInfos 의 command·durationMs)
  - 묻기(ask)의 결과: 같은 toolUseID 의 도구 결과가 오류면 거부, 아니면 허용

결과에는 프로젝트 이름과 대화 내용 조각이 들어가므로 저장소 밖(기본 ~/.claude/harness-reports/)에 쓴다.

사용:
  python3 harness_report.py [--projects-dir ~/.claude/projects] [--since 2026-10-01] [--out DIR]
                            [--include-tmp] [--decision-log DECISION_LOG.md]
"""

import argparse
import collections
import datetime
import glob
import json
import os
import re
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

#: 은퇴한 훅 → 그 훅의 알림 꼬리표(없으면 None). 파일은 없어도 보존된 대화 기록에는 남아 있어 같은 행으로 읽어야 한다.
RETIRED_HOOKS = {"comprehension-ledger-stale-guard.py": "COMPREHENSION-LEDGER-STALE", "skill-usage-auto.py": None}
#: 이 엔진의 훅 파일 이름 — 명령 경로에서 「하네스 훅인가」와 「어느 설치인가」를 가린다
ENGINE_HOOKS = {os.path.basename(p) for p in glob.glob(os.path.join(HERE, "*.py"))
                if not os.path.basename(p).startswith("test_")} | set(RETIRED_HOOKS)
HOOK_ERROR = re.compile(r"^PreToolUse:\w+ hook error: \[(.*?)\]: ", re.S)
PY_NAME = re.compile(r"([\w.-]+\.py)")
NOTICE_TAG = re.compile(r"^\[([A-Z0-9][A-Z0-9_-]+)\]")
COMMAND_NAME = re.compile(r"<command-name>/(?:[\w-]+:)?([\w-]+)</command-name>")
AUTO_MODE_DENIAL = "denied by the Claude Code auto mode classifier"
SAFETY_DENIAL = "denied by a built-in Claude Code safety check"
#: 알림 본문에서 따로 셀 문구 — DECISION_LOG 예측이 이 수를 기다린다
SPECIAL_NOTICES = {"tamper_session_commit": "이번 세션 커밋", "comprehension_earlier_plan": "이전 계획의 미답 질문"}
#: 문맥 비용에서 「하네스 몫」으로 셀 스킬 — skills/ 의 폴더 이름과 같아야 한다(시험이 대조한다).
#: 설치본에는 skills/ 가 옆에 없어서 목록을 박아 둔다.
HARNESS_SKILLS = {"gate-a", "gate-b", "gate-c", "gate-d", "gate-e", "audit", "doc-cleanup", "init", "harness-update"}
SKILL_BODY = re.compile(r"^Base directory for this skill: (\S+)")
#: Gate B 질문이 답을 기다린다는 표지 — gate-b 의 「다음 단계」 문구, 그리고 질문을 세션 문서에 적을 때의 평가 자리표시.
#: v1.7.0 전 회차에는 둘 다 없어 응답의 「질문 N」도 본다(실제 기록 12회에서 질문 회차와 정확히 일치했다).
GATE_B_WAITING = re.compile(r"위 질문에 답해 주세요|질문\s*[1-9]")
GATE_B_PLACEHOLDER = re.compile(r"\*\*평가\*\*\s*[:：]\s*\(\s*(?:답변\s*후\s*기록|평가\s*전|filled after the answer)\s*\)")
GATE_B_SKIP = re.compile(r"스킵|스킴|skip", re.I)       # 「스킴」은 실제 기록의 오타
GATE_B_SKIP_MAX = 40                                    # 긴 글 안의 「스킵」은 답이다(실제 스킵은 7~9자였다)
GATE_B_GO = re.compile(r"(?:(?:계획대로 )?구현|진행|계속|gate[ -]?c(?: 시작)?)(?:해라|해)?[.!]?", re.I)
GATE_B_PLAN = re.compile(r"\*\*계획 변경\*\*\s*[:：]\s*(있음|없음)")
GATE_B_ASKED = ("answered", "partial", "skipped", "unanswered")


def as_text(value):
    """기록의 문자열 칸이 목록·숫자로 오는 경우가 있다(실제 기록에서 확인) — 모두 문자열로 읽는다."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(as_text(v.get("text", v) if isinstance(v, dict) else v) for v in value)
    return json.dumps(value, ensure_ascii=False)


def engine_source(command):
    """하네스 훅 명령 → 설치 형태. 하네스 훅이 아니면 None."""
    names = PY_NAME.findall(command or "")
    if not names or names[-1] not in ENGINE_HOOKS:
        return None
    if "/plugins/cache/" in command or "CLAUDE_PLUGIN_ROOT" in command:
        return "plugin"
    if ".claude/hooks/patrick-work-harness" in command:
        return "install.sh"
    if "plans/hooks/" in command:
        return "source-copy"
    return "other"


def _notice_owners():
    """알림 꼬리표 → 그 꼬리표를 내는 엔진 훅 파일. Stop 훅 알림에는 명령이 남지 않아 꼬리표로만 보이는데, 같은 훅의
    실행 시간은 파일 이름으로 남는다 — 둘을 한 행으로 합쳐야 훅 수를 바로 센다(2026-10-28 대조 검증에서 두 행으로 나뉜 것을
    두 훅으로 셌다). 두 파일 이상에 나오는 꼬리표는 주인을 정할 수 없어 꼬리표 그대로 둔다."""
    owners = collections.defaultdict(set)
    for name in ENGINE_HOOKS - {os.path.basename(__file__)}:
        try:
            text = open(os.path.join(HERE, name), encoding="utf-8").read()
        except OSError:
            continue
        for tag in re.findall(r"[\"']\[([A-Z][A-Z0-9_-]+)\]", text):
            owners[tag].add(name)
    return {tag: next(iter(files)) for tag, files in owners.items() if len(files) == 1}


NOTICE_OWNERS = {**_notice_owners(), **{tag: name for name, tag in RETIRED_HOOKS.items() if tag}}


def guard_name(command="", content="", fallback=""):
    names = PY_NAME.findall(command or "")
    if names:
        return names[-1]
    tag = NOTICE_TAG.match((content or "").strip())
    return NOTICE_OWNERS.get(tag.group(1), tag.group(1)) if tag else (fallback or "?")


def parse_output(stdout):
    """훅 stdout 의 JSON 결정을 읽는다. JSON 이 아니면 빈 dict."""
    text = (stdout or "").strip()
    if not text:
        return {}
    for candidate in (text, text.splitlines()[-1]):
        try:
            data = json.loads(candidate)
            return data if isinstance(data, dict) else {}
        except ValueError:
            continue
    return {}


def _texts(content):
    if isinstance(content, str):
        return [content]
    if isinstance(content, list):
        return [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
    return []


def _is_typed_prompt(event):
    if event.get("type") != "user" or event.get("isSidechain"):
        return False
    if event.get("isMeta") or event.get("isCompactSummary") or event.get("isVisibleInTranscriptOnly"):
        return False
    content = (event.get("message") or {}).get("content")
    if isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
        return False
    text = " ".join(_texts(content)).strip()
    return bool(text) and not text.startswith(("<local-command", "[Request interrupted"))


def _new_guard():
    return collections.Counter()


def gate_b_rounds(path):
    """Gate B 회차마다 사람이 질문에 어떻게 응답했는지 센다. 반환: 0 이 아닌 칸만 담은 dict.

    왜: Gate 순서만 보면 9초 만의 스킵도 정상 `gate-b→gate-c` 다 — 질문 회차가 스킵으로 끝나던 2026-10 을 사용 집계기는
    「이상 패턴 없음」으로 냈다. 회차는 Gate 호출로 열리고, 스킵·다음 Gate 호출·기록 끝, 또는 모델이 다시 묻지 않고
    넘어간 뒤의 사람 입력에서 닫힌다 — Gate C 호출 없이 구현으로 넘어가는 대화가 있어 호출만 기다리면 회차가 끝나지 않는다.

    칸: none 질문 없음 · answered 답함 · partial 일부 답 뒤 스킵 · skipped 답 없이 스킵 · unanswered 답도 스킵도 없이 끝남,
    plan_changed·plan_same 평가 아래 적은 「계획 변경」(있음이 하나라도 있으면 있음).

    한계: Skill·슬래시 호출 없이 진행한 회차는 못 본다(하한). 「답함」은 글자만 본다 — 되묻기나 불만도 답으로 센다(상한).
    """
    from gate_transcript import GATE_COMMAND, GATE_SKILL, WRITE_TOOLS, _written_texts

    counts = collections.Counter()
    current = None

    def close():
        nonlocal current
        if current is None:
            return
        if not current["asked"]:
            counts["none"] += 1
        elif current["skipped"]:
            counts["partial" if current["answers"] else "skipped"] += 1
        else:
            counts["answered" if current["answers"] else "unanswered"] += 1
        if current["plan"]:
            counts["plan_changed" if "있음" in current["plan"] else "plan_same"] += 1
        current = None

    def called(letter):
        nonlocal current
        close()
        if letter == "b":
            current = {"asked": False, "waiting": False, "answers": 0, "skipped": False, "plan": set()}

    def waiting():
        current["asked"] = current["waiting"] = True

    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if not isinstance(event, dict) or event.get("isSidechain"):
                continue
            content = (event.get("message") or {}).get("content")
            if event.get("type") == "assistant" and isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "text" and current and GATE_B_WAITING.search(as_text(block.get("text"))):
                        waiting()
                    elif block.get("type") == "tool_use":
                        inp = block.get("input") or {}
                        m = GATE_SKILL.search(str(inp.get("skill", ""))) if block.get("name") == "Skill" else None
                        if m:
                            called(m.group(1))
                        elif current:
                            for text in _written_texts(block.get("name"), inp)[1]:
                                # Bash 명령에는 지울 옛 글자도 들어 있다 — 자리표시는 쓴 글자만 보이는 도구에서 읽는다
                                if block.get("name") in WRITE_TOOLS and GATE_B_PLACEHOLDER.search(text):
                                    waiting()
                                current["plan"].update(GATE_B_PLAN.findall(text))
            elif _is_typed_prompt(event):
                text = " ".join(_texts(content)).strip()
                letters = GATE_COMMAND.findall(text)
                for letter in letters:
                    called(letter)
                if letters or not current or text.startswith("<"):       # `<task-notification>` 등은 사람 답이 아니다
                    continue
                if not current["waiting"]:
                    close()
                    continue
                current["waiting"] = False         # 다시 물으면 위 표지가 도로 켠다 — 맨 「구현」 뒤의 지시는 답이 아니다
                if GATE_B_SKIP.search(text) and len(text) <= GATE_B_SKIP_MAX:
                    current["skipped"] = True
                    close()
                elif not GATE_B_GO.fullmatch(text):
                    current["answers"] += 1
    close()
    return dict(counts)


def read_session(path):
    """대화 기록 한 개 → 세션 행. 반환: (행, 해석하지 못한 줄 수)."""
    from gate_transcript import AUTONOMOUS_APPROVAL, _TAGGED, gate_sequence

    row = {"session": os.path.splitext(os.path.basename(path))[0], "project": "", "first": "", "last": "",
           "models": collections.Counter(), "user_prompts": 0, "cross_check_requests": 0,
           "batch_requests": 0, "autonomous_approvals": 0, "skills": collections.Counter(),
           "auto_mode_denials": 0, "safety_check_denials": 0, "special": collections.Counter()}
    guards = collections.defaultdict(_new_guard)
    durations = collections.defaultdict(list)
    sources, notices, asks, ask_owner = set(), collections.Counter(), {}, {}
    # 문맥 비용: 응답마다 실린 입력 토큰(입력+캐시 생성+캐시 읽기). 한 응답이 내용 블록마다 여러 줄로 남으므로
    # message.id 로 묶는다. 스킬 본문은 적재 직전·직후 응답의 문맥 차로 잰다.
    call_index, calls, stops, loads = {}, [], [], []
    bad = 0
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                event = json.loads(line)
            except ValueError:
                bad += 1
                continue
            if not isinstance(event, dict):
                continue
            ts = event.get("timestamp") or ""
            if ts:
                row["first"] = min(row["first"] or ts, ts)
                row["last"] = max(row["last"], ts)
            if not row["project"] and event.get("cwd"):
                row["project"] = os.path.basename(event["cwd"].rstrip("/"))
            kind = event.get("type")
            if kind == "assistant" and not event.get("isSidechain"):
                message = event.get("message") or {}
                if message.get("model") and message["model"] != "<synthetic>":
                    row["models"][message["model"]] += 1
                    usage = message.get("usage")
                    if isinstance(usage, dict):
                        mid = message.get("id") or event.get("uuid") or len(calls)
                        size = sum(usage.get(k) or 0 for k in
                                   ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
                        if mid not in call_index:
                            call_index[mid] = len(calls)
                            calls.append(size)
                            stops.append(None)
                        calls[call_index[mid]] = size
                        stops[call_index[mid]] = message.get("stop_reason") or stops[call_index[mid]]
                for block in message.get("content") or []:
                    if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "Skill":
                        row["skills"][str((block.get("input") or {}).get("skill", "")).split(":")[-1]] += 1
            elif kind == "user":
                content = (event.get("message") or {}).get("content")
                for text in (_texts(content) if isinstance(content, list) else []):
                    body = SKILL_BODY.match(text)
                    if body:
                        loads.append((os.path.basename(body.group(1).rstrip("/")), len(calls)))
                if _is_typed_prompt(event):
                    text = " ".join(_texts(content))
                    row["user_prompts"] += 1
                    row["cross_check_requests"] += "대조 검증" in text
                    row["batch_requests"] += ("C~E 일괄" in text) or ("D~E 일괄" in text)
                    row["autonomous_approvals"] += AUTONOMOUS_APPROVAL in _TAGGED.sub("", text)
                    for name in COMMAND_NAME.findall(text):
                        row["skills"][name] += 1
                if isinstance(content, list):
                    for block in content:
                        if not (isinstance(block, dict) and block.get("type") == "tool_result"):
                            continue
                        text = block.get("content")
                        text = text if isinstance(text, str) else json.dumps(text, ensure_ascii=False)
                        tid = block.get("tool_use_id")
                        if tid in asks:
                            asks[tid] = "denied" if block.get("is_error") else "allowed"
                        if AUTO_MODE_DENIAL in text:
                            row["auto_mode_denials"] += 1
                        if SAFETY_DENIAL in text:
                            row["safety_check_denials"] += 1
                        m = HOOK_ERROR.match(text)
                        if m:
                            guards[guard_name(m.group(1))]["deny"] += 1
                            guards[guard_name(m.group(1))]["fired"] += 1
                            src = engine_source(m.group(1))
                            if src:
                                sources.add(src)
            elif kind == "attachment":
                att = event.get("attachment") or {}
                atype = str(att.get("type", ""))
                if not atype.startswith("hook"):
                    continue
                command = as_text(att.get("command"))
                src = engine_source(command)
                if src:
                    sources.add(src)
                name = guard_name(command, as_text(att.get("content")), as_text(att.get("hookName")))
                if isinstance(att.get("durationMs"), (int, float)) and command:
                    durations[name].append(att["durationMs"])
                g = guards[name]
                if atype == "hook_system_message":
                    text = as_text(att.get("content")).strip()
                    g["notice"] += 1
                    g["fired"] += 1
                    notices[text.splitlines()[0] if text else ""] += 1
                    for key, needle in SPECIAL_NOTICES.items():
                        row["special"][key] += needle in text
                elif atype == "hook_additional_context":
                    g["context"] += 1
                    g["fired"] += 1
                elif atype == "hook_blocking_error":
                    g["block"] += 1
                    g["fired"] += 1
                elif atype == "hook_non_blocking_error":
                    g["error"] += 1
                elif atype == "hook_success":
                    out = parse_output(as_text(att.get("stdout")))
                    spec = out.get("hookSpecificOutput") or {}
                    decision = spec.get("permissionDecision")
                    fired = False
                    if decision in ("ask", "deny"):
                        g[decision] += 1
                        fired = True
                        if decision == "ask" and att.get("toolUseID"):
                            asks[att["toolUseID"]] = "unknown"
                            ask_owner[att["toolUseID"]] = name
                    if out.get("decision") == "block":
                        g["block"] += 1
                        fired = True
                    if out.get("continue") is False:
                        g["stop"] += 1
                        fired = True
                    if fired:
                        g["fired"] += 1
            elif kind == "system" and event.get("subtype") == "stop_hook_summary":
                for info in event.get("hookInfos") or []:
                    command = as_text(info.get("command") if isinstance(info, dict) else "")
                    src = engine_source(command)
                    if src:
                        sources.add(src)
                        if isinstance(info.get("durationMs"), (int, float)):
                            durations[guard_name(command)].append(info["durationMs"])

    for tid, outcome in asks.items():
        guards[ask_owner.get(tid, "?")]["ask_" + outcome] += 1
    seq = gate_sequence(path) or []
    row["gates"] = " ".join(seq)
    row["c_to_e"] = sum(1 for a, b in zip(seq, seq[1:]) if (a, b) == ("c", "e"))
    row["gate_b"] = gate_b_rounds(path) if "b" in seq else {}
    row["engine_source"] = sorted(sources)
    out_guards = {}
    for name, counter in guards.items():
        entry = {k: v for k, v in counter.items() if v}
        times = durations.get(name) or []
        if times:
            entry["ms_median"] = int(statistics.median(times))
            entry["ms_max"] = int(max(times))
        if entry:
            out_guards[name] = entry
    for name, times in durations.items():
        if name not in out_guards and times:
            out_guards[name] = {"ms_median": int(statistics.median(times)), "ms_max": int(max(times))}
    row["guards"] = out_guards
    text, count = (notices.most_common(1)[0] if notices else ("", 0))
    row["max_repeat_notice"] = {"count": count, "text": text[:160]}
    for key in ("models", "skills", "special"):
        row[key] = dict(row[key])
    skill_loads, harness_tokens = collections.defaultdict(list), 0
    for name, k in loads:                      # k = 적재 뒤 첫 응답의 위치
        if 0 < k < len(calls):
            jump = calls[k] - calls[k - 1]
            skill_loads[name].append(jump)
            if name in HARNESS_SKILLS:
                harness_tokens += jump * (len(calls) - k)   # 적재 뒤 모든 응답에 다시 실린다(상한 — 같이 들어온 입력 포함)
    row["context"] = {"calls": len(calls), "first": calls[0] if calls else 0, "max": max(calls, default=0),
                      "input_total": sum(calls), "max_tokens_stops": stops.count("max_tokens"),
                      "skill_loads": dict(skill_loads), "harness_skill_tokens": harness_tokens}
    return row, bad


def collect(projects_dir, since=None, include_tmp=False):
    """projects 폴더의 최상위 대화 기록(하위 에이전트 기록 제외)을 모두 읽는다."""
    sessions, bad, failed = [], 0, []
    for path in sorted(glob.glob(os.path.join(projects_dir, "*", "*.jsonl"))):
        folder = os.path.basename(os.path.dirname(path))
        if not include_tmp and folder.startswith("-tmp-"):
            continue
        try:
            row, b = read_session(path)
        except Exception as e:  # 형식이 낯선 기록 하나가 보고서 전체를 멈추면 안 된다 — 세어서 보고한다
            failed.append(f"{folder}/{os.path.basename(path)}: {type(e).__name__}: {e}")
            continue
        bad += b
        if since and (row["last"] or "")[:10] < since:
            continue
        row["folder"] = folder
        sessions.append(row)
    return {"sessions": sessions, "bad_lines": bad, "failed_sessions": failed}


# ── DECISION_LOG 예측 진행 ─────────────────────────────────────────────
# 제목 앞부분 → (세는 방법, 확인 시점의 목표, 설명). 세는 방법이 None 이면 이 스크립트로 셀 수 없고,
# 설명이 자료 출처다. 새 결정을 기록하면 여기에 한 줄을 더한다(없으면 「미등록」으로 보고된다).
def _sum(key):
    return lambda rows: sum(r.get(key, 0) for r in rows)


def _guard(name, field):
    return lambda rows: sum(r["guards"].get(name, {}).get(field, 0) for r in rows)


def _a_to_c(rows):
    """Gate A 다음 Gate B 없이 Gate C 로 간 세션 수 — skill_usage_aggregator 의 「이해도 생략(a→c)」과 같은 기준.
    Gate 순서는 스킬 호출만 센다 — 일괄 중 스킬을 부르지 않고 진행한 Gate 는 보이지 않는다(하한)."""
    count = 0
    for r in rows:
        after_a = False
        for g in (r.get("gates") or "").split():
            if g == "a":
                after_a = True
            elif g == "b":
                after_a = False
            elif g == "c" and after_a:
                count += 1
                break
    return count


def _skill(name):
    return lambda rows: sum(r["skills"].get(name, 0) for r in rows)


def _special(key):
    return lambda rows: sum(r["special"].get(key, 0) for r in rows)


def _gate_a(rows):
    return sum(r["gates"].split().count("a") for r in rows)


def _gate_b_asked(rows):
    return sum((r.get("gate_b") or {}).get(k, 0) for r in rows for k in GATE_B_ASKED)


METRICS = [
    ("Gate A 가 과거 교훈을", _gate_a, 20, "Gate A 실행 수. 「교훈 조회」 절 유무는 아카이브에서 본다"),
    ("「교훈 조회」 절을 Stop 훅으로", _gate_a, 20, "Gate A 실행 수(위 항목과 같은 자료)"),
    ("/init 과 /harness-update 가 교훈", _skill("harness-update"), 1, "/harness-update 실행 수"),
    ("error_topics 항목은", None, 20, "교훈 파일(error_topics) — 새 항목의 근거 칸"),
    ("엔진 배포 파일 일관성", None, 3, "엔진 저장소 git log — 손 수정 커밋"),
    ("교훈마다 엔진/프로젝트", None, 20, "교훈 파일의 「엔진 후보」 표시"),
    ("문구 변경의 재생 비교", None, None, "사용자 결정"),
    ("시험 쓰기 가드는", _guard("test-write-guard.py", "ask"), 1, "시험 쓰기 가드의 확인 창 수"),
    ("변조 가드는 세션 중 커밋도", _special("tamper_session_commit"), 10, "세션 커밋 경고 수(오탐 여부는 사람이 판정)"),
    ("이해도 대기 가드는", _special("comprehension_earlier_plan"), 10, "「이전 계획의 미답 질문」 알림 수"),
    ("사용 집계기는", _sum("c_to_e"), None, "C 직후 E(검증 누락) 수 — 확인 시점 2027-01"),
    ("「C~E 일괄」「D~E 일괄」", _sum("batch_requests"), 5, "일괄 요청 수(Gate D 실행 여부는 세션의 gates 열)"),
    ("Gate 스킬의 대시보드 배선", None, None, "엔진 저장소의 hooks.json 변경"),
    ("/init 세션 문서 틀", _skill("init"), 1, "/init 실행 수"),
    ("Gate A 가 레인을 판정하되", None, None, "아카이브의 레인 판정 절, 재생 측정"),
    ("레인 범위 가드는 쓰기 전에", _guard("lane-scope-guard.py", "ask"), 10, "레인 가드 확인 창 수"),
    ("자율 레인은 일괄 실행에", _sum("autonomous_approvals"), 10, "「자율 레인 승인」 수 — 판정은 카드 원장"),
    ("레인 가드는 플러그인과 install.sh", _guard("lane-scope-guard.py", "fired"), None, "레인 가드 발동 수와 소요 시간(세션 표)"),
    ("레인 가드가 Gate D 기록을", _sum("autonomous_approvals"), 10, "「자율 레인 승인」 수"),
    ("사전 등록 — 자율 레인의", _sum("autonomous_approvals"), 20, "「자율 레인 승인」 수 — 판정은 카드 원장"),
    ("하네스 문맥 비용을 사용 보고서가", lambda rows: sum(1 for r in rows if _engine_skill_session(r)), 10,
     "최신 엔진(플러그인·install.sh)으로 하네스 스킬을 적재한 세션 수 — 몫은 「문맥 비용」 표"),
    ("모델 판정 재생은 사례마다 두 번", None, None, "다음 재생 측정"),
    ("docker 가드는 남기되", _guard("docker-command-guard.py", "deny"), 10, "docker 가드 거부 수(정탐 여부는 사람이 판정)"),
    ("사용 보고서는 알림 꼬리표를", None, None, "월간 보고서 가드 표의 대문자 꼬리표 행 수"),
    ("이해도 원장 만료 알림은 최근 만료", None, None, "원장의 verified 갱신 수(R0 전후 한 달)"),
    ("최신 엔진 대조 실험", None, None, "어려운 과제 대조 실험(재료는 저장소 밖)"),
    ("제품 저장소의 실제 과거 작업 재생", None, None, "계약을 문장에 적지 않은 재생 실험"),
    ("Gate E 가드가 이 대화에서 Gate D", _guard("gate-e-sync-guard.py", "block"), 10, "Gate E 가드 차단 수(사유는 메시지 — 오탐은 사람이 판정)"),
    ("제품 저장소 재생 2차", None, None, "범위 가드 절차를 고칠지의 사용자 결정"),
    ("범위 가드 확인 실험", None, None, "일괄 중 FIX-B 이월·Gate B 전 일괄 승인 처리의 사용자 결정"),
    ("일괄 승인이 Gate B 전에 와도", _a_to_c, None, "Gate A 다음 Gate B 없이 Gate C 로 간 세션 수(스킬 호출 기준, 하한) — 확인 시점 R0 뒤 한 달"),
    ("사용 집계기가 플러그인 스킬 이름을", None, None, "다음 월간 집계(skill_usage_aggregator)와 다음 동기화의 린트"),
    ("커밋 메시지 가드가 -am", None, 3, "엔진 저장소 릴리스 — 정당한 커밋이 막힌 경우"),
    ("Gate B 스킵은 증거가 아니다", _gate_b_asked, 20, "Gate B 질문 회차 수 — 결과는 「Gate B 질문 결과」 표, 스킵 행 통과는 대화 기록"),
    ("Gate B 는 되돌리기 어려운 변경에만", _gate_b_asked, 10, "Gate B 질문 회차 수 — 답함·스킵은 「Gate B 질문 결과」 표"),
    ("이해도 원장 만료 알림 훅과", None, None, "R0 뒤 사용 보고서의 훅 오류 수"),
    ("자체 점검 결함을 고친다", None, None, "R0 뒤 사용 보고서의 Gate 순서와 가드 차단 수"),
    ("skill-usage-auto 훅과 빈 문서를 뺀다", None, None, "R0 뒤 사용 보고서의 훅 오류 수"),
    ("Gate 산출물은 대시보드 위쪽", None, None, "R0 뒤 「문맥 비용」 표의 스킬 적재량과 사용자 지적 수(세션 원장)"),
    ("가드 3종은 남긴다", None, None, "R0 뒤 사용 보고서의 가드 차단 수(사본별)·docker 거부 10회"),
    ("Gate E 는 설정한 경로에", None, None, "R0 뒤 아카이브 첫 줄의 final_status 와 경로(사용자 확인)"),
]


def _engine_skill_session(row):
    loads = (row.get("context") or {}).get("skill_loads") or {}
    return bool(set(row.get("engine_source") or []) & {"plugin", "install.sh"}) and bool(set(loads) & HARNESS_SKILLS)


def pending_entries(decision_log):
    text = open(decision_log, encoding="utf-8").read()
    out = []
    for block in re.split(r"\n(?=### \[)", text):
        m = re.match(r"### \[(\d{4}-\d{2}-\d{2})\] (.+)", block)
        result = re.search(r"\*\*결과\*\*:[ \t]*(.*)", block)
        if m and result and not result.group(1).strip():
            out.append((m.group(1), m.group(2).strip()))
    return out


def prediction_progress(decision_log, sessions):
    progress = []
    for date, title in pending_entries(decision_log):
        rows = [r for r in sessions if (r.get("last") or "")[:10] >= date]
        metric = next((m for m in METRICS if title.startswith(m[0])), None)
        if metric is None:
            progress.append({"date": date, "title": title, "countable": False, "count": None, "target": None,
                             "source": "미등록 — harness_report.py METRICS 에 한 줄 추가"})
            continue
        prefix, fn, target, source = metric
        progress.append({"date": date, "title": title, "countable": fn is not None,
                         "count": fn(rows) if fn else None, "target": target, "source": source})
    return progress


# ── 출력 ───────────────────────────────────────────────────────────────
def render(data, progress, projects_dir, since):
    sessions = data["sessions"]
    hook_events = sum(len(r["guards"]) for r in sessions)   # 실행 기록이든 발동이든 훅 흔적이 있는 가드 수
    lines = [f"# 하네스 사용 보고서 — {datetime.date.today().isoformat()}", "",
             f"- 읽은 곳: `{projects_dir}`" + (f" (마지막 활동 {since} 이후)" if since else ""),
             f"- 세션 {len(sessions)}개 · 해석하지 못한 줄 {data['bad_lines']}개 · 읽지 못한 대화 기록 {len(data.get('failed_sessions', []))}개"]
    lines += [f"  - {f}" for f in data.get("failed_sessions", [])[:10]]
    if not sessions or hook_events == 0:
        lines.append("- ⚠️ **형식 확인 필요** — 세션이나 훅 기록이 하나도 없다. 대화 기록 형식이 바뀌었거나 경로가 틀렸을 수 있다.")
    by_project = collections.defaultdict(list)
    for r in sessions:
        by_project[r["project"] or r["folder"]].append(r)
    lines += ["", "## 프로젝트", "", "| 프로젝트 | 세션 | 하네스 출처 | 모델(응답 수) | 사용자 입력 | 대조 검증 요청 |", "|---|---|---|---|---|---|"]
    for name, rows in sorted(by_project.items()):
        src = sorted({s for r in rows for s in r["engine_source"]}) or ["(하네스 훅 없음)"]
        models = collections.Counter()
        for r in rows:
            models.update(r["models"])
        lines.append(f"| {name} | {len(rows)} | {', '.join(src)} | "
                     f"{', '.join(f'{m} {n}' for m, n in models.most_common(3))} | "
                     f"{sum(r['user_prompts'] for r in rows)} | {sum(r['cross_check_requests'] for r in rows)} |")
    total = collections.defaultdict(collections.Counter)
    times = collections.defaultdict(list)
    for r in sessions:
        for name, g in r["guards"].items():
            total[name].update({k: v for k, v in g.items() if not k.startswith("ms_")})
            if "ms_median" in g:
                times[name].append(g["ms_max"])
    def is_harness(name):  # 엔진 훅 파일이거나, 엔진 훅이 쓰는 대문자 알림 꼬리표
        return name in ENGINE_HOOKS or bool(re.fullmatch(r"[A-Z0-9][A-Z0-9_-]+", name))

    ordered = sorted(total.items(), key=lambda x: (not is_harness(x[0]), -x[1].get("fired", 0)))
    lines += ["", "## 가드 (하네스 훅 먼저, 그 아래는 다른 훅)", "",
              "| 가드 | 발동 | 묻기(허용/거부/모름) | 거부 | 차단 | 멈춤 | 알림 | 맥락 | 오류 | 가장 느린 실행(ms) |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for name, c in ordered:
        name_cell = name if is_harness(name) else f"(기타) {name}"
        lines.append(f"| {name_cell} | {c['fired']} | {c['ask']} ({c['ask_allowed']}/{c['ask_denied']}/{c['ask_unknown']}) | "
                     f"{c['deny']} | {c['block']} | {c['stop']} | {c['notice']} | {c['context']} | {c['error']} | "
                     f"{max(times[name]) if times[name] else '—'} |")
    lines += ["", f"- auto 모드 분류기 거부 {sum(r['auto_mode_denials'] for r in sessions)}회 · "
                  f"내장 안전 검사 거부 {sum(r['safety_check_denials'] for r in sessions)}회"]
    repeats = sorted((r for r in sessions if r["max_repeat_notice"]["count"] >= 3),
                     key=lambda r: -r["max_repeat_notice"]["count"])
    lines += ["", "## 반복된 알림 (한 세션에서 같은 알림 3회 이상 — 경고 피로 후보)", ""]
    lines += [f"- {r['project']} `{r['session'][:8]}`: {r['max_repeat_notice']['count']}회 — {r['max_repeat_notice']['text']}"
              for r in repeats[:15]] or ["- 없음"]
    lines += ["", "## 문맥 비용 (응답마다 실린 입력 토큰)", "",
              "- 첫 응답 문맥 = 시스템 프롬프트·도구·CLAUDE.md·스킬 목록의 고정 몫. 하네스 없는 프로젝트의 값과 비교한다.",
              "- 하네스 스킬 몫 = 하네스 스킬 적재로 늘어난 문맥 × 적재 뒤 응답 수 ÷ 입력 합(상한 — 같은 차례의 입력 포함).", "",
              "| 프로젝트 | 세션 | 응답 | 첫 응답 문맥 | 최대 문맥 | 스킬 적재(토큰) | 하네스 스킬 몫 | 출력 한도 중단 |",
              "|---|---|---|---|---|---|---|---|"]
    for r in sorted(sessions, key=lambda r: r["last"], reverse=True):
        c = r.get("context") or {}
        if not c.get("calls"):
            continue
        loads = ", ".join(f"{n} {'/'.join(str(j) for j in js)}" for n, js in sorted(c["skill_loads"].items())) or "—"
        share = f"{100 * c['harness_skill_tokens'] / c['input_total']:.0f}%" if c["input_total"] else "—"
        lines.append(f"| {r['project']} | `{r['session'][:8]}` | {c['calls']} | {c['first']} | {c['max']} | "
                     f"{loads} | {share} | {c['max_tokens_stops']} |")
    lines += ["", "## Gate 순서 (세션별)", "", "| 프로젝트 | 세션 | 마지막 활동 | Gate | C 직후 E |", "|---|---|---|---|---|"]
    for r in sorted(sessions, key=lambda r: r["last"], reverse=True):
        if r["gates"]:
            lines.append(f"| {r['project']} | `{r['session'][:8]}` | {r['last'][:10]} | {r['gates']} | {r['c_to_e']} |")
    lines += ["", "## Gate B 질문 결과 (회차별 사람의 응답)", "",
              "- Gate 순서가 아니라 질문에 어떻게 응답했는지 본다. Skill·슬래시 호출 없이 진행한 회차는 빠진다(하한).",
              "- 「답함」은 글자만 본다 — 되묻기나 불만도 답으로 센다(상한). 답의 정오와 사람의 실제 이해는 재지 않는다.",
              "- 스킵 수 하나로 판단하지 않는다 — 낮아도 의례일 수 있고 높아도 정당할 수 있다. 계획 변경 칸은 gate-b Step 3 이 적기 시작한 뒤 회차부터 쌓인다.", "",
              "| 프로젝트 | 세션 | 마지막 활동 | 질문 없음 | 답함 | 일부 답 뒤 스킵 | 스킵 | 답 없음 | 계획 변경 있음/없음 |",
              "|---|---|---|---|---|---|---|---|---|"]
    gate_b_cols = ("none", "answered", "partial", "skipped", "unanswered")
    gate_b_total = collections.Counter()
    for r in sorted(sessions, key=lambda r: r["last"], reverse=True):
        g = r.get("gate_b") or {}
        if g:
            gate_b_total.update(g)
            lines.append(f"| {r['project']} | `{r['session'][:8]}` | {r['last'][:10]} | "
                         + " | ".join(str(g.get(k, 0)) for k in gate_b_cols)
                         + f" | {g.get('plan_changed', 0)}/{g.get('plan_same', 0)} |")
    lines.append("| 합계 | | | " + " | ".join(str(gate_b_total[k]) for k in gate_b_cols)
                 + f" | {gate_b_total['plan_changed']}/{gate_b_total['plan_same']} |")
    if progress is not None:
        lines += ["", "## DECISION_LOG 대기 예측의 진행", "",
                  "| 결정일 | 결정 | 지금 | 확인 시점 목표 | 자료 |", "|---|---|---|---|---|"]
        for p in progress:
            now = p["count"] if p["countable"] else "셀 수 없음"
            lines.append(f"| {p['date']} | {p['title'][:60]} | {now} | {p['target'] if p['target'] is not None else '—'} | {p['source']} |")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="하네스 사용 보고서")
    parser.add_argument("--projects-dir", default=os.path.expanduser("~/.claude/projects"))
    parser.add_argument("--since", default="", help="마지막 활동이 이 날짜(YYYY-MM-DD) 이후인 세션만")
    parser.add_argument("--out", default="", help="출력 폴더(기본 ~/.claude/harness-reports/<오늘>)")
    parser.add_argument("--include-tmp", action="store_true", help="-tmp- 로 시작하는 시험용 프로젝트도 넣는다")
    parser.add_argument("--decision-log", default="", help="대기 예측 진행표를 만들 DECISION_LOG.md")
    args = parser.parse_args(argv)
    out = args.out or os.path.join(os.path.expanduser("~/.claude/harness-reports"), datetime.date.today().isoformat())
    data = collect(args.projects_dir, since=args.since or None, include_tmp=args.include_tmp)
    decision_log = args.decision_log or os.path.join(os.path.dirname(HERE), "DECISION_LOG.md")
    progress = prediction_progress(decision_log, data["sessions"]) if os.path.isfile(decision_log) else None
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "sessions.jsonl"), "w", encoding="utf-8") as f:
        for row in data["sessions"]:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with open(os.path.join(out, "report.md"), "w", encoding="utf-8") as f:
        f.write(render(data, progress, args.projects_dir, args.since))
    print(f"보고서: {os.path.join(out, 'report.md')} (세션 {len(data['sessions'])}개)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
