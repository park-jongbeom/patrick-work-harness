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
  - 압축(2.1.312~2.1.319 에서 확인, 2026-11-10): system `compact_boundary`(compactMetadata.trigger·preTokens), 요약은
    isCompactSummary 사용자 줄, 자동 압축 뒤 다시 붙은 스킬은 `invoked_skills` 첨부, 파일은 `file` 첨부
  - 스킬 다시 싣기: 본문은 「Base directory for this skill:」 로 시작하는 목록 모양 사용자 줄, 같은 내용의 재호출은
    문자열 모양의 「Skill /x is already loaded above」 한 줄

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
import shutil
import statistics
import sys
import tempfile

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
#: Stop 훅의 exit 2 차단은 `stop_hook_summary.hookErrors` 에 이 모양으로만 남는다(첨부 없음, 2026-11-05 실제 기록).
#: 같은 칸의 다른 줄 — 실행 실패(`Failed to run`·`non-blocking status`)와 JSON 차단 본문 — 은 첨부에도 남아 거기서 센다.
STOP_EXIT2 = re.compile(r"^\[(.*?)\]: ", re.S)
PY_NAME = re.compile(r"([\w.-]+\.py)")
NOTICE_TAG = re.compile(r"^\[([A-Z0-9][A-Z0-9_-]+)\]")
COMMAND_NAME = re.compile(r"<command-name>/(?:[\w-]+:)?([\w-]+)</command-name>")
AUTO_MODE_DENIAL = "denied by the Claude Code auto mode classifier"
SAFETY_DENIAL = "denied by a built-in Claude Code safety check"
#: 알림 본문에서 따로 셀 문구 — DECISION_LOG 예측이 이 수를 기다린다
SPECIAL_NOTICES = {"tamper_session_commit": "이번 세션 커밋", "comprehension_earlier_plan": "이전 계획의 미답 질문"}
#: 문맥 비용에서 「하네스 몫」으로 셀 스킬 — skills/ 의 폴더 이름과 같아야 한다(시험이 대조한다).
#: 설치본에는 skills/ 가 옆에 없어서 목록을 박아 둔다.
HARNESS_SKILLS = {"gate-a", "gate-b", "gate-c", "gate-d", "gate-e", "audit", "doc-cleanup", "init", "harness-update",
                  "harness-feedback", "commit-up"}
SKILL_BODY = re.compile(r"^Base directory for this skill: (\S+)")
#: 같은 스킬을 같은 내용으로 다시 부르면 본문 대신 붙는 한 줄(2.1.312·2.1.319 실제 기록) — 인자를 주거나 직접 입력하면 본문이 다시 실린다
LOADED_NOTE = re.compile(r"^Skill /(?:[\w-]+:)?([\w-]+) is already loaded above")
#: 글자 → 토큰 어림. 세션 안에 깨끗하게 잰 적재(앞뒤 응답 사이에 압축이 없는 것)가 있으면 그 비율을, 없으면 이 값을 쓴다.
#: 엔진 스킬 다섯 개의 본문 글자 수와 노트북 실측 적재량(2026-11-10)의 비가 0.40~0.52 였다.
TOKENS_PER_CHAR = 0.45
#: 문맥에 실리는 첨부 → 「문맥 출처」 칸. 도구 목록·환경 같은 시스템 첨부는 첫 응답 문맥에 이미 들어 있어 세지 않는다.
#: 대기 중 입력(queued_command)은 뒤에 사용자 메시지로 다시 남지 않는다(이 서버 기록 305건 확인) — 여기서 센다.
#: Gate A 승인 표지 — gate-a 가 승인으로 읽는 문구(「진행」「ok」 는 승인이 아니다). 다음 Gate 호출도 승인 뒤로 본다.
APPROVAL_PHRASE = re.compile(r"Gate\s*A\s*승인|계획대로\s*구현|Gate\s*A\s*대로\s*구현|자율\s*레인\s*승인|[CD]\s*~\s*E\s*일괄")
#: 코드 편집으로 세는 도구. Bash 로 쓴 편집(sed -i·리다이렉트)은 셀 수 없어 하한이다.
CODE_EDIT_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def _is_code(path):
    """계획·기록 문서(.md·.txt)와 하네스 설정(.claude/)은 코드 편집이 아니다 — Gate A 가 승인 전에 쓰는 것들이다."""
    p = str(path).replace("\\", "/").lower()
    return not (p.endswith((".md", ".markdown", ".txt")) or "/.claude/" in p or p.endswith("session-dashboard.html"))


CONTEXT_ATTACHMENTS = {"invoked_skills": "reattach:skills", "file": "reattach:files", "instructions": "instructions",
                       "nested_memory": "instructions", "hook_additional_context": "hook_context"}
#: 새 문맥 검토(fresh_review.py, 2026-11-10)의 흔적 — 검토자 지시문 첫머리 표지, Gate A 블록에 쓴 기록 줄(자리표시 `지적 N` 은
#: 빼고 숫자나 「실패」만), 하위 에이전트가 뒤에서 돌았을 때의 완료 알림(`queue-operation` 줄 — 사용량은 여기에만 남는다).
FRESH_MARKER = "[새 문맥 검토]"
TIMESTAMP = re.compile(r'"timestamp"\s*:\s*"([^"]+)"')
#: 스크립트를 실제로 부른 명령만 — 파일 이름을 grep·cat 으로 말한 명령은 아니다(이 엔진의 개발 대화에서 22건이 섞였다).
FRESH_RUN = re.compile(r"python[0-9.]*(?:\.exe)?[\"']?\s+(?:-\S+\s+)*[\"']?[^\s\"']*fresh_review\.py")
FRESH_RECORD = re.compile(r"^[ \t]*[-*][ \t]+\*\*새 문맥 검토\*\*[ \t]*[:：][ \t]*((?:지적[ \t]*\d|실패)[^\n]*)$", re.M)
TASK_USAGE = re.compile(r"<tool-use-id>([^<]+)</tool-use-id>.*?<subagent_tokens>(\d+)</subagent_tokens>"
                        r".*?<duration_ms>(\d+)</duration_ms>")
#: Gate B 질문이 답을 기다린다는 표지 — gate-b 의 「다음 단계」 문구, 그리고 질문을 세션 문서에 적을 때의 평가 자리표시.
#: v1.7.0 전 회차에는 둘 다 없어 응답의 「질문 N」도 본다(실제 기록 12회에서 질문 회차와 정확히 일치했다).
GATE_B_WAITING = re.compile(r"위 질문에 답해 주세요|질문\s*[1-9]|「진행」이라고 답하면")
#: 확인형 Gate B(2026-11-10) — 질문 대신 되돌리기 어려운 부분·가장 깨지기 쉬운 곳·되돌리는 법 세 줄을 보이고 「진행」 한 마디로 넘어간다.
GATE_B_CONFIRM = re.compile(r"「진행」이라고 답하면")
GATE_B_ACK = re.compile(r"(?:확인|진행|계속|ok|오케이|좋아|구현)(?:했다|함|해|해라|합니다|하자)?[.!]?", re.I)
GATE_B_PLACEHOLDER = re.compile(r"\*\*평가\*\*\s*[:：]\s*\(\s*(?:답변\s*후\s*기록|평가\s*전|filled after the answer)\s*\)")
GATE_B_SKIP = re.compile(r"스킵|스킴|skip", re.I)       # 「스킴」은 실제 기록의 오타
GATE_B_SKIP_MAX = 40                                    # 긴 글 안의 「스킵」은 답이다(실제 스킵은 7~9자였다)
GATE_B_GO = re.compile(r"(?:(?:계획대로 )?구현|진행|계속|gate[ -]?c(?: 시작)?)(?:해라|해)?[.!]?", re.I)
GATE_B_PLAN = re.compile(r"\*\*계획 변경\*\*\s*[:：]\s*(있음|없음)")
GATE_B_ASKED = ("confirmed", "answered", "partial", "skipped", "unanswered")


def as_text(value):
    """기록의 문자열 칸이 목록·숫자로 오는 경우가 있다(실제 기록에서 확인) — 모두 문자열로 읽는다."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(as_text(v.get("text", v) if isinstance(v, dict) else v) for v in value)
    return json.dumps(value, ensure_ascii=False)


def _text_size(value):
    """첨부의 글자 수 — 중첩된 칸의 문자열만 더한다(JSON 으로 바꾸면 이스케이프가 글자로 세진다)."""
    if isinstance(value, str):
        return len(value)
    if isinstance(value, dict):
        return sum(_text_size(v) for v in value.values())
    if isinstance(value, list):
        return sum(_text_size(v) for v in value)
    return 0


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

    칸: none 질문 없음 · confirmed 확인형 회차를 「진행」으로 넘김 · answered 답함(확인형에서 묻거나 바꾼 것 포함) ·
    partial 일부 답 뒤 스킵 · skipped 답 없이 스킵 · unanswered 답도 스킵도 없이 끝남,
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
            counts["answered" if current["answers"] else "confirmed" if current["confirmed"] else "unanswered"] += 1
        if current["plan"]:
            counts["plan_changed" if "있음" in current["plan"] else "plan_same"] += 1
        current = None

    def called(letter):
        nonlocal current
        close()
        if letter == "b":
            current = {"asked": False, "waiting": False, "answers": 0, "skipped": False, "plan": set(),
                       "confirm": False, "confirmed": False}

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
                        current["confirm"] = current["confirm"] or bool(GATE_B_CONFIRM.search(as_text(block.get("text"))))
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
                elif current["confirm"] and (GATE_B_GO.fullmatch(text) or GATE_B_ACK.fullmatch(text)):
                    current["confirmed"] = True       # 확인형에서는 「진행」이 정식 응답이다
                elif not GATE_B_GO.fullmatch(text):
                    current["answers"] += 1
    close()
    return dict(counts)


def _fresh_verdict(output):
    """fresh_review.py 출력에서 판정 줄 → (첫 줄, 「발동」·「미실행」·「실패」 또는 None). 한 명령에 다른 스크립트를 이어 붙이면
    첫 줄은 그 스크립트의 것이다(2026-11-12 — Gate B 판정기도 「발동 —」로 시작한다). 그래서 「미실행 —」「실패 —」 줄, 또는 바로
    다음에 Agent 호출 지시가 오는 「발동 —」 줄을 찾는다."""
    lines = [ln.strip() for ln in (output or "").strip().splitlines()]
    for i, line in enumerate(lines):
        if line.startswith(("미실행 —", "실패 —")):
            return lines[0], line.split()[0]
        if line.startswith("발동 —") and any(ln.startswith("Agent 도구를") for ln in lines[i + 1:i + 3]):
            return lines[0], "발동"
    first = lines[0] if lines else ""
    return first, ("발동" if first.startswith("발동 —") else None)


def read_session(path):
    """대화 기록 한 개 → 세션 행. 반환: (행, 해석하지 못한 줄 수)."""
    from gate_transcript import AUTONOMOUS_APPROVAL, GATE_SKILL, WRITE_TOOLS, _TAGGED, _written_texts, gate_sequence

    row = {"session": os.path.splitext(os.path.basename(path))[0], "project": "", "first": "", "last": "",
           "models": collections.Counter(), "user_prompts": 0, "cross_check_requests": 0,
           "batch_requests": 0, "autonomous_approvals": 0, "skills": collections.Counter(),
           "auto_mode_denials": 0, "safety_check_denials": 0, "special": collections.Counter()}
    guards = collections.defaultdict(_new_guard)
    durations = collections.defaultdict(list)
    sources, notices, asks, ask_owner = set(), collections.Counter(), {}, {}
    notice_owner = {}                               # 알림 첫 줄 → 그 알림을 낸 훅(보낼 때 문구를 거르는 기준)
    # 문맥 비용: 응답마다 실린 입력 토큰(입력+캐시 생성+캐시 읽기). 한 응답이 내용 블록마다 여러 줄로 남으므로
    # message.id 로 묶는다. 스킬 본문은 적재 직전·직후 응답의 문맥 차로 잰다.
    call_index, calls, stops, loads = {}, [], [], []
    bad = 0
    gate_calls, blocked = set(), 0                  # 훅이 막은 Gate 호출(2026-11-10)
    fresh, fresh_calls, review_calls, review_usage, notified, records = collections.Counter(), {}, set(), {}, {}, set()
    # 문맥 회계(2026-11-10): 무엇이 언제(응답 위치 = 그때까지의 응답 수, 사건 순번 seq) 들어와 다음 압축까지 몇 응답에
    # 실렸는지 센다. 압축 경계 뒤에는 앞의 내용이 빠진다.
    seq, names, boundaries, items, images = 0, {}, [], [], []
    reattached, gate_a_starts, dups, skill_calls, typed_at = [], [], set(), {}, {}
    present, reload, versions, fresh_heads = set(), collections.Counter(), set(), []
    reload_by = collections.defaultdict(collections.Counter)   # 스킬별 다시 싣기 방식(2026-11-12)
    gate_events, approvals, code_edits = [], [], []  # 승인 전 편집(2026-11-10): (seq, Gate 글자) · 승인 입력 seq · (코드 편집 seq, 프로젝트 안?)
    cwd = ""
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                event = json.loads(line)
            except ValueError:
                bad += 1
                continue
            if not isinstance(event, dict):
                continue
            seq += 1
            side = bool(event.get("isSidechain"))
            if event.get("version") and not side:
                versions.add(str(event["version"]))
            if "<task-notification>" in line:
                for m in TASK_USAGE.finditer(line):
                    notified.setdefault(m.group(1), (int(m.group(2)), int(m.group(3))))
            ts = event.get("timestamp") or ""
            if ts:
                row["first"] = min(row["first"] or ts, ts)
                row["last"] = max(row["last"], ts)
            if event.get("cwd"):
                cwd = str(event["cwd"])
                if not row["project"]:
                    row["project"] = os.path.basename(cwd.rstrip("/"))
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
                    if isinstance(block, dict) and block.get("type") == "text":
                        items.append((len(calls), seq, "model:text", len(as_text(block.get("text")))))
                    if not (isinstance(block, dict) and block.get("type") == "tool_use"):
                        continue
                    name, tid = block.get("name"), block.get("id")
                    inp = block.get("input") if isinstance(block.get("input"), dict) else {}
                    names[tid] = name
                    items.append((len(calls), seq, "model:tool_input", len(json.dumps(inp, ensure_ascii=False))))
                    target = inp.get("file_path") or inp.get("notebook_path") or ".md"
                    if name in CODE_EDIT_TOOLS and _is_code(target):
                        code_edits.append((seq, _in_project(target, cwd)))
                    if name == "Skill":
                        skill = str(inp.get("skill", ""))
                        row["skills"][skill.split(":")[-1]] += 1
                        skill_calls[skill.split(":")[-1]] = (seq, bool(str(inp.get("args") or "").strip()))
                        if tid and GATE_SKILL.search(skill):
                            gate_calls.add(tid)
                    elif name in ("Bash", "PowerShell") and FRESH_RUN.search(str(inp.get("command", ""))):
                        fresh_calls[tid] = "--force" in str(inp.get("command", ""))
                    elif name in ("Agent", "Task") and str(inp.get("prompt", "")).lstrip().startswith(FRESH_MARKER):
                        review_calls.add(tid)
                    elif name in WRITE_TOOLS:
                        for written in _written_texts(name, inp)[1]:
                            records.update(m.group(1).strip() for m in FRESH_RECORD.finditer(written))
            elif kind == "user":
                content = (event.get("message") or {}).get("content")
                for text in _texts(content):
                    for typed_name in COMMAND_NAME.findall(text[:400]):
                        typed_at[typed_name] = seq
                    # 「already loaded」 줄은 본문과 달리 내용이 문자열로 남는다(실제 기록 7건 모두)
                    note = LOADED_NOTE.match(text)
                    if note and note.group(1) in HARNESS_SKILLS and not side:
                        reload["notes"] += 1
                        if re.fullmatch(r"gate-[a-e]", note.group(1)):
                            gate_events.append((seq, note.group(1)[-1]))
                        if note.group(1) == "gate-a":
                            gate_a_starts.append(len(calls))
                if event.get("isCompactSummary") and not side:
                    items.append((len(calls), seq, "summary", len(" ".join(_texts(content)))))
                if isinstance(content, list) and not side:      # 사용자가 붙여 넣은 이미지(도구 결과의 이미지는 아래에서)
                    images.extend((len(calls), seq) for b in content if isinstance(b, dict) and b.get("type") == "image")
                for text in (_texts(content) if isinstance(content, list) else []):
                    body = SKILL_BODY.match(text)
                    if body:
                        # 윈도 기록을 다른 컴퓨터에서 읽어도 `\` 로 나눈다(os.path 는 그 컴퓨터의 구분자만 안다)
                        name = re.split(r"[\\/]", body.group(1).rstrip("/\\"))[-1]
                        loads.append((name, len(calls), len(text), seq))
                        if side:
                            continue
                        items.append((len(calls), seq, "skill:harness" if name in HARNESS_SKILLS else "skill:other", len(text)))
                        if name in HARNESS_SKILLS:
                            call = skill_calls.get(name)
                            mode = ("typed" if seq - typed_at.get(name, -99) <= 8 else
                                    ("args" if call[1] else "tool") if call and seq - call[0] <= 8 else "other")
                            reload[mode] += 1
                            reload_by[name][mode] += 1
                            if re.fullmatch(r"gate-[a-e]", name):
                                gate_events.append((seq, name[-1]))
                            if name in present:             # 앞 사본이 아직 문맥에 있다(그사이 압축 없음)
                                dups.add(seq)
                                reload_by[name]["dup"] += 1
                            present.add(name)
                            if name == "gate-a":
                                gate_a_starts.append(len(calls))
                if _is_typed_prompt(event):
                    text = " ".join(_texts(content))
                    items.append((len(calls), seq, "user", len(text)))
                    if APPROVAL_PHRASE.search(text):
                        approvals.append(seq)
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
                        raw = block.get("content")
                        text = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
                        # 글 부분과 이미지 — 이미지의 base64 를 글자로 세면 출처가 뒤틀린다(이 서버 Read 결과의 96%가 이미지였다)
                        parts = raw if isinstance(raw, list) else []
                        plain = text if isinstance(raw, str) else "\n".join(
                            as_text(p.get("text")) for p in parts if isinstance(p, dict) and p.get("type") == "text")
                        tid = block.get("tool_use_id")
                        if not side:
                            items.append((len(calls), seq, "tool:" + str(names.get(tid, "?")), len(plain)))
                            images.extend((len(calls), seq) for p in parts if isinstance(p, dict) and p.get("type") == "image")
                        if tid in gate_calls and block.get("is_error"):
                            blocked += 1
                        if tid in fresh_calls:
                            first, verdict = _fresh_verdict(plain)
                            key = (("forced" if fresh_calls.pop(tid) else "fired") if verdict == "발동"
                                   else "not_run" if verdict == "미실행"
                                   else "failed" if verdict == "실패" else "unknown")
                            fresh[key] += 1
                            if key == "unknown":                # 하네스 스크립트가 낸 첫 줄이라 제품 내용이 아니다
                                fresh_heads.append(("목록 " if parts else "") + first[:80])
                        if tid in review_calls:
                            res = event.get("toolUseResult")
                            if isinstance(res, dict) and isinstance(res.get("totalTokens"), int):
                                review_usage[tid] = (res["totalTokens"], res.get("totalDurationMs") or 0)
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
                if not side and atype == "invoked_skills":     # 자동 압축 뒤 다시 붙은 스킬 본문
                    for s in att.get("skills") or []:
                        if isinstance(s, dict):
                            n = len(as_text(s.get("content")))
                            items.append((len(calls), seq, CONTEXT_ATTACHMENTS[atype], n))
                            reattached.append((str(s.get("name", "")).split(":")[-1], len(calls), seq, n))
                elif not side and atype == "queued_command":
                    prompt = as_text(att.get("prompt"))
                    items.append((len(calls), seq, "notification" if prompt.lstrip().startswith("<task-notification>")
                                  else "user", len(prompt)))
                elif not side and atype in CONTEXT_ATTACHMENTS:
                    value = att.get("content") if atype == "file" else {k: v for k, v in att.items() if k != "type"}
                    items.append((len(calls), seq, CONTEXT_ATTACHMENTS[atype], _text_size(value)))
                if not atype.startswith("hook"):
                    continue
                command = as_text(att.get("command"))
                src = engine_source(command)
                if src:
                    sources.add(src)
                name = guard_name(command, as_text(att.get("content")), as_text(att.get("hookName")))
                if atype == "hook_blocking_error":   # JSON 차단 — 명령이 없어 본문의 꼬리표·스크립트 이름으로 주인을 찾는다
                    be = att.get("blockingError")
                    text = as_text(be.get("blockingError") if isinstance(be, dict) else be).strip()
                    tag, scripts = NOTICE_TAG.match(text), PY_NAME.findall(text)
                    name = NOTICE_OWNERS.get(tag.group(1), tag.group(1)) if tag else (scripts[0] if scripts else name)
                if isinstance(att.get("durationMs"), (int, float)) and command:
                    durations[name].append(att["durationMs"])
                g = guards[name]
                if atype == "hook_system_message":
                    text = as_text(att.get("content")).strip()
                    g["notice"] += 1
                    g["fired"] += 1
                    first_line = text.splitlines()[0] if text else ""
                    notices[first_line] += 1
                    notice_owner.setdefault(first_line, name)
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
            elif kind == "system" and event.get("subtype") == "compact_boundary" and not side:
                meta = event.get("compactMetadata") or {}
                boundaries.append((len(calls), seq, "manual" if meta.get("trigger") == "manual" else "auto",
                                   meta.get("preTokens")))
                present.clear()
            elif kind == "system" and event.get("subtype") == "stop_hook_summary":
                for err in event.get("hookErrors") or []:
                    text = as_text(err)
                    m = STOP_EXIT2.match(text)
                    if m:
                        g = guards[guard_name(m.group(1), text[m.end():])]
                        g["block"] += 1
                        g["fired"] += 1
                        src = engine_source(m.group(1))
                        if src:
                            sources.add(src)
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
    row["blocked_gate_calls"] = blocked
    if fresh or review_calls or records:
        usage = [u for u in (review_usage.get(t) or notified.get(t) for t in review_calls) if u]
        row["fresh_review"] = {**dict(fresh), "reviews": len(review_calls), "tokens": [u[0] for u in usage],
                               "ms": [u[1] for u in usage], "records": sorted(records)}
        if fresh_heads:
            row["fresh_review"]["unknown_heads"] = fresh_heads[:5]
    row["cc_versions"] = sorted(versions, key=lambda v: (_version_key(v) or (), v))
    row["edits"] = _edit_timing(gate_events, approvals, code_edits)
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
    row["max_repeat_notice"] = {"count": count, "text": text[:160], "owner": notice_owner.get(text, "")}
    for key in ("models", "skills", "special"):
        row[key] = dict(row[key])
    row["context"] = {"calls": len(calls), "first": calls[0] if calls else 0, "max": max(calls, default=0),
                      "input_total": sum(calls), "max_tokens_stops": stops.count("max_tokens"),
                      **_context_accounting(calls, loads, boundaries, items, images, reattached, gate_a_starts,
                                            dups, reload)}
    row["context"]["reloads"]["by_skill"] = {k: dict(v) for k, v in reload_by.items()}
    return row, bad


def _in_project(path, cwd):
    """편집한 파일이 프로젝트(대화의 작업 폴더) 안인가. 상대 경로는 안이다. 윈도·리눅스 표기를 함께 본다."""
    p = str(path).replace("\\", "/")
    if not (p.startswith("/") or re.match(r"[A-Za-z]:/", p)):
        return True
    root = str(cwd or "").replace("\\", "/").rstrip("/")
    return bool(root) and p.lower().startswith(root.lower() + "/")


def _edit_timing(gate_events, approvals, code_edits):
    """코드 편집이 Gate 회차의 어디에서 났나. 바로 앞 Gate 가 A 이고 그 뒤 승인 입력이 없으면 「승인 전」, 바로 앞 Gate 가
    E 이거나 그 세션에서 Gate 를 아직 부르지 않았으면 「회차 밖」. Gate 를 한 번도 부르지 않은 세션은 회차 밖으로 세지 않는다.
    승인 전 편집은 프로젝트 안의 파일만 센다 — 임시 스크립트·메시지 파일은 따로 센다(2026-11-12, 받은 자료에서 가를 수 없었다)."""
    events = sorted(gate_events)
    pre, pre_out, outside, cycles = 0, 0, 0, set()
    for at, inside in code_edits:
        last = next((g for g in reversed(events) if g[0] < at), None)
        if last is None:
            outside += bool(events)
        elif last[1] == "a" and not any(last[0] < a < at for a in approvals):
            if inside:
                pre += 1
                cycles.add(last[0])
            else:
                pre_out += 1
        elif last[1] == "e":
            outside += 1
    return {"code": len(code_edits), "pre_approval": pre, "pre_approval_cycles": len(cycles),
            "pre_approval_outside": pre_out, "outside_cycle": outside}


def _context_accounting(calls, loads, boundaries, items, images, reattached, gate_a_starts, dups, reload):
    """압축을 반영한 스킬 몫·회차 이월·문맥 출처·스킬 다시 싣기 (2026-11-10).

    위치 k 에 들어온 것은 응답 k 부터 다음 압축 경계(그 뒤 사건)의 위치 전까지 실린다. 옛 계산은 적재 뒤 모든 응답에
    실린다고 보아 압축으로 빠진 본문까지 셌고, 압축과 겹친 적재는 큰 음수가 되어 오히려 뺐다."""
    cut = {b[0] for b in boundaries}

    def resident(pos, at):
        for bpos, bseq, _, _ in boundaries:
            if bseq > at:
                return max(0, bpos - pos)
        return max(0, len(calls) - pos)

    # 앞뒤 응답 사이에 압축이 없는 적재만 문맥 차로 잰다 — 그 비율로 나머지(압축과 겹친 적재·다시 붙은 사본)를 어림한다
    clean = [(calls[k] - calls[k - 1], chars) for _, k, chars, _ in loads
             if 0 < k < len(calls) and k not in cut and calls[k] > calls[k - 1]]
    clean_chars = sum(c for _, c in clean)
    ratio = sum(j for j, _ in clean) / clean_chars if clean_chars else TOKENS_PER_CHAR
    skill_loads, harness_tokens, dup_tokens = collections.defaultdict(list), 0, 0
    for name, k, chars, at in loads:           # k = 적재 뒤 첫 응답의 위치
        if k >= len(calls):
            continue
        valid = 0 < k and k not in cut and calls[k] > calls[k - 1]
        tokens = calls[k] - calls[k - 1] if valid else int(chars * ratio)
        skill_loads[name].append(tokens)
        if name in HARNESS_SKILLS:
            harness_tokens += tokens * resident(k, at)        # 상한 — 같은 차례에 함께 들어온 입력이 섞인다
            if at in dups:
                dup_tokens += tokens
    for name, k, at, chars in reattached:
        if name in HARNESS_SKILLS and k < len(calls):
            harness_tokens += int(chars * ratio) * resident(k, at)
    # 회차 이월: Gate A 를 부르기 직전 문맥 − 첫 응답 문맥. 새 대화 어림 절감: 회차마다 새 대화로 시작했다면 그 회차의
    # 응답마다 이월만큼 덜 실렸을 것(가정 — 회차 안에서 늘어나는 양은 같다). 회차 안에서 압축되면 그 뒤로는 0.
    first = calls[0] if calls else 0
    starts = sorted(set(gate_a_starts))
    carry, saving = [], 0
    for i, p in enumerate(starts):
        if not 0 < p < len(calls):
            continue
        end = starts[i + 1] if i + 1 < len(starts) else len(calls)
        c = 0 if p in cut else max(0, calls[p - 1] - first)
        carry.append(c)
        stop = min([b for b in cut if p < b <= end] + [end])
        saving += sum(min(c, max(0, calls[j] - first)) for j in range(p, stop))
    sources = collections.Counter()
    for pos, at, cat, n in items:
        if n and pos < len(calls):
            sources[cat] += n * resident(pos, at)
    return {"skill_loads": dict(skill_loads), "harness_skill_tokens": harness_tokens,
            "compactions": {"auto": sum(1 for b in boundaries if b[2] == "auto"),
                            "manual": sum(1 for b in boundaries if b[2] == "manual"),
                            "pre_tokens": [b[3] for b in boundaries if isinstance(b[3], int)]},
            "cycles": len(starts), "carry": carry, "fresh_saving": saving,
            "reloads": {**{k: reload.get(k, 0) for k in ("typed", "tool", "args", "other")}, "dup": len(dups),
                        "dup_tokens": dup_tokens, "notes": reload.get("notes", 0)},
            "sources": dict(sources),
            "images": {"count": sum(1 for p, _ in images if p < len(calls)),
                       "resident": sum(resident(p, at) for p, at in images if p < len(calls))}}


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


def version_segments(path, row, seen):
    """갱신 전에 열어 갱신 뒤에도 이어 쓴 대화 → 버전마다 「그 버전을 처음 본 뒤」 부분만 다시 센 행들 (2026-11-12).

    받은 자료의 하네스 대화 둘이 11-09 에 열려 11-12 까지 이어져(응답 1,600개 안팎), 세션 시작 버전으로 거르는 예측표가
    갱신 뒤 사건까지 모두 버렸다. 그 시각 이후 줄만 담은 임시 사본을 같은 방식으로 읽는다 — 문맥 표에는 쓰지 않고 예측에만 쓴다."""
    out = []
    first, last = (row.get("first") or "")[:19], (row.get("last") or "")[:19]
    for version, at in sorted((seen or {}).items(), key=lambda kv: kv[1]):
        at = (at or "")[:19]
        if not (first < at < last):
            continue
        tmp = tempfile.mkdtemp(prefix="harness-segment-")
        try:
            part = os.path.join(tmp, os.path.basename(path))
            keep = False
            with open(path, encoding="utf-8", errors="replace") as src, open(part, "w", encoding="utf-8") as dst:
                for line in src:
                    ts = TIMESTAMP.search(line[:4000])
                    if ts:
                        keep = ts.group(1)[:19] >= at
                    if keep:
                        dst.write(line)
            seg, _ = read_session(part)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        seg.update(session=row.get("session"), segment=version, folder=row.get("folder", ""))
        out.append(seg)
    return out


def load_sessions(paths, since=None):
    """다른 컴퓨터의 `--out` 이 남긴 sessions.jsonl 을 읽는다. 실제 작업이 노트북에서 돌고 대화 기록은 거기에만 있어서,
    집계는 노트북에서 하고 예측 대조는 DECISION_LOG 가 있는 이 저장소에서 한다(2026-11-05)."""
    sessions = []
    for path in paths:
        if not os.path.isfile(path):
            sys.exit(f"세션 기록 파일이 없습니다: {path}")
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    row = json.loads(line)
                    if not since or (row.get("last") or "")[:10] >= since:
                        sessions.append(row)
    # 받는 폴더에는 같은 세션이 보낼 때마다 다시 온다(최근 30일 전체를 보낸다) — 마지막 활동이 가장 늦은 행만 남긴다.
    latest = {}
    for row in sessions:
        key = (row.get("session") or id(row), row.get("segment") or "")
        if key not in latest or (row.get("last") or "") >= (latest[key].get("last") or ""):
            latest[key] = row
    return {"sessions": list(latest.values()), "bad_lines": 0, "failed_sessions": []}


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


def _fresh(key):
    return lambda rows: sum((r.get("fresh_review") or {}).get(key, 0) for r in rows)


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
    ("원본 쪽 이름은 커밋하지 않는 목록에", None, None, "다음 sync-from-source.sh 실행과 릴리스 전 린트"),
    ("공개 이력은 다시 쓰지 않는다", None, None, "다음 릴리스 3회의 본문 검사"),
    ("보고서는 다른 컴퓨터의 세션 기록을", None, None, "R0 뒤 노트북에서 받은 첫 sessions.jsonl"),
    ("변조 가드는 git 출력을 UTF-8 로", _guard("test-tampering-guard.py", "error"), None,
     "변조 가드 실행 오류 수 — R0 뒤 0 이어야 한다(R0 전 노트북 131)"),
    ("커밋 메시지 가드는 Bash|PowerShell 에", _guard("commit-msg-guard.py", "deny"), None,
     "커밋 메시지 가드 거부 수 — PowerShell 커밋인지는 대화 기록의 도구 이름으로 본다"),
    ("훅이 막은 Skill 호출은 Gate 순서에", _sum("blocked_gate_calls"), None,
     "훅이 막은 Gate 호출 수 — 막힌 글자가 Gate 순서에서 빠졌는지는 「Gate 순서」 표"),
    ("Gate A 계획을 대화 밖 검토자가", _fresh("fired"), 10,
     "발동한 새 문맥 검토 수(--force 제외) — 내용 고침·올림·건너뜀은 「새 문맥 검토」 표"),
    ("작업 PC 의 사용 기록 요약을 응답 종료 훅이", len, None,
     "결정일 뒤 활동한 받은 세션 수 — 받은 세션 전체와 PC 별 마지막 전송·이유·엔진 버전은 `harness-feedback-sync.py receive` 출력"),
    ("Gate B 를 시험에서 확인으로 바꾼다", lambda rows: _gate_b_asked(rows), 10,
     "멈춘 Gate B 회차 수 — 확인(진행)·답함·계획 변경은 「Gate B 질문 결과」 표, 판단 기준은 이 결정의 예측 칸"),
    ("외부 평가의 남은 항목 — 보존 권장을 90일로", lambda rows: sum((r.get("edits") or {}).get("pre_approval_cycles", 0) for r in rows),
     None, "승인 전 코드 편집이 있던 Gate A 회차 수 — 「코드 편집 시점」 표, 판단은 갱신 뒤 하네스 세션 10개(이 결정의 예측 칸)"),
    ("외부 평가가 짚은 문서 과장과 꺼진 체크섬을", None, 3,
     "릴리스 자산 두 파일(`gh release view vX.Y.Z --json assets`)·설치 출력의 「SHA256 검증 완료」·린트 35·36 오탐 — 다음 릴리스 3회"),
    ("요약이 압축·회차 이월·문맥 출처를 센다", lambda rows: sum(1 for r in rows if _accounted(r)), 10,
     "새 항목이 든 하네스 세션 수 — 판단 기준은 이 결정의 예측 칸, 값은 「문맥 비용」「문맥 출처」「스킬 다시 싣기」 표"),
    ("대시보드 맨 윗줄에 하네스 버전을 보인다", None, None,
     "사용자 확인 — 갱신한 PC 의 대시보드 맨 윗줄과 세션 원장 새 행의 `engine_version.source`"),
    ("받은 자료로 측정 결함 셋을 고치고", lambda rows: sum(1 for r in rows if r.get("gates")), 10,
     "갱신 뒤 하네스 세션 수 — 세션당 Gate A 회차·이월은 「문맥 비용」 표, 승인 전 편집은 「코드 편집 시점」 표, 다시 싣기는 스킬별 칸"),
    ("대시보드는 다시 그려지면 맨 위부터", None, None, "사용자 확인 — 갱신한 PC 의 대시보드 첫 화면, Gate E 뒤 next_action 길이"),
    ("회차 끝의 정리·audit 판정·커밋을", _skill("commit-up"), 10,
     "`/commit-up` 실행 수 — doc-cleanup 호출 수 대 본문 적재 수는 「문맥 비용」 표의 스킬 적재 칸, 다시 시킨 회차는 사용자 확인"),
]


def _accounted(row):
    return bool(row.get("gates")) and "compactions" in (row.get("context") or {})


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


def _version_key(version):
    try:
        return tuple(int(x) for x in str(version).split("."))
    except ValueError:
        return None


def release_dates(changelog):
    """CHANGELOG 의 `## [X.Y.Z] - 날짜` → [(날짜, 버전)] 날짜순. 설치본에는 CHANGELOG 가 없다 — 그때는 빈 목록."""
    try:
        with open(changelog, encoding="utf-8") as f:
            text = f.read()
    except (OSError, TypeError):
        return []
    found = re.findall(r"^## \[(\d+(?:\.\d+)*)\] - (\d{4}-\d{2}-\d{2})", text, re.M)
    return sorted(((d, v) for v, d in found), key=lambda x: (x[0], _version_key(x[1]) or ()))


def _shipped_in(releases, date):
    """결정이 실린 릴리스를 git 으로 알 수 없을 때 — 결정일 이후 첫 릴리스."""
    return _version_key(next((v for d, v in releases if d >= date), None))


def shipped_versions(decision_log):
    """결정 제목 줄 → 그 줄이 처음 들어간 릴리스 태그의 버전. git 이 없거나 저장소가 아니면 None(결정일로 짐작한다).

    결정일로 짐작하면 같은 날 릴리스가 여럿일 때 가장 이른 것으로 묶였다 — 11-10 결정 넷은 1.19.0~1.20.0 에 실렸는데 1.18.0
    으로 잡혔다(2026-11-12). 커밋했지만 아직 릴리스하지 않은 결정은 빈 값이다(실린 판이 없다)."""
    import subprocess

    folder, name = os.path.split(os.path.abspath(decision_log))

    def git(*args):
        p = subprocess.run(["git", "-C", folder, *args], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", stdin=subprocess.DEVNULL, timeout=60)
        return p.stdout if p.returncode == 0 else None

    try:
        blame = git("blame", "--line-porcelain", "--", name)
    except (OSError, subprocess.SubprocessError):
        return None
    if not blame:
        return None
    heads, commit = {}, None
    for line in blame.splitlines():
        if re.match(r"^[0-9a-f]{40} ", line):
            commit = line.split()[0]
        elif line.startswith("\t### [") and commit:
            heads[line[1:].strip()] = commit
    out, tags = {}, {}
    for head, commit in heads.items():
        if commit not in tags:
            found = None if set(commit) == {"0"} else git("describe", "--contains", "--match", "v[0-9]*", commit)
            m = re.match(r"v(\d+(?:\.\d+)*)", (found or "").strip())
            tags[commit] = m.group(1) if m else ""
        out[head] = tags[commit]
    return out


def _rows_after(sessions, shipped, date, releases):
    """결정이 실린 뒤의 행만. 세션마다 하나: 그 버전 이상에서 시작한 세션은 전체 행, 아니면 그 버전 이상을 처음 본 뒤의
    부분 행(segment) 중 가장 이른 것. 갱신 시각이 없는 행(이 서버의 기록)은 결정일로 거른다."""
    groups = collections.defaultdict(list)
    for r in sessions:
        groups[r.get("session") or id(r)].append(r)
    out = []
    for rows in groups.values():
        full = next((r for r in rows if not r.get("segment")), None)
        if full is not None and not ("engine_at_start" in full and releases):
            if (full.get("last") or "")[:10] >= date:
                out.append(full)
            continue
        have = _version_key(full.get("engine_at_start")) if full is not None and full.get("engine_at_start") else None
        if full is not None and have and shipped and have >= shipped:
            out.append(full)
            continue
        later = sorted((_version_key(r["segment"]), r) for r in rows if r.get("segment") and shipped
                       and (_version_key(r["segment"]) or ()) >= shipped)
        if later:
            out.append(later[0][1])
    return out


def prediction_progress(decision_log, sessions, changelog=None):
    """대기 예측마다 지금까지의 수. 갱신 시각이 기록된 PC 의 행(`engine_at_start` 칸이 있다)은 그 결정이 든 릴리스 뒤의
    부분만 센다 — 결정일로 세면 갱신 전 세션이 섞였고(2026-11-10), 세션 시작으로 세면 갱신 전에 열어 이어 쓴 대화가 통째로
    빠졌다(2026-11-12). 그래서 버전별 부분 행(`segment`)을 쓴다."""
    progress = []
    releases = release_dates(changelog) if changelog else []
    by_git = shipped_versions(decision_log) if releases else None
    for date, title in pending_entries(decision_log):
        head = f"### [{date}] {title}"
        shipped = (_version_key(by_git[head]) if by_git[head] else None) if by_git and head in by_git \
            else _shipped_in(releases, date)
        rows = _rows_after(sessions, shipped, date, releases)
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
def _top_sources(sources, n=5):
    total = sum(sources.values())
    if not total:
        return "—"
    return ", ".join(f"{k} {100 * v / total:.0f}%" for k, v in collections.Counter(sources).most_common(n))


def render(data, progress, projects_dir, since):
    sessions = [r for r in data["sessions"] if not r.get("segment")]   # 버전별 부분 행은 예측에만 쓴다
    hook_events = sum(len(r["guards"]) for r in sessions)   # 실행 기록이든 발동이든 훅 흔적이 있는 가드 수
    lines = [f"# 하네스 사용 보고서 — {datetime.date.today().isoformat()}", "",
             f"- 읽은 곳: `{projects_dir}`" + (f" (마지막 활동 {since} 이후)" if since else ""),
             f"- 세션 {len(sessions)}개 · 해석하지 못한 줄 {data['bad_lines']}개 · 읽지 못한 대화 기록 {len(data.get('failed_sessions', []))}개"]
    lines += [f"  - {f}" for f in data.get("failed_sessions", [])[:10]]
    if not sessions or hook_events == 0:
        lines.append("- ⚠️ **형식 확인 필요** — 세션이나 훅 기록이 하나도 없다. 대화 기록 형식이 바뀌었거나 경로가 틀렸을 수 있다.")
    by_project = collections.defaultdict(list)
    for r in sessions:
        by_project[r.get("project") or r.get("folder") or "?"].append(r)
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
    lines += [f"- {r['project']} `{r['session'][:8]}`: {r['max_repeat_notice']['count']}회 — "
              + (r['max_repeat_notice']['text']
                 or f"({r['max_repeat_notice'].get('owner') or '다른 훅'} 의 알림 — 문구는 보내지 않았다)")
              for r in repeats[:15]] or ["- 없음"]
    lines += ["", "## 문맥 비용 (응답마다 실린 입력 토큰)", "",
              "- 첫 응답 문맥 = 시스템 프롬프트·도구·CLAUDE.md·스킬 목록의 고정 몫. 하네스 없는 프로젝트의 값과 비교한다.",
              "- 하네스 스킬 몫 = 스킬 본문 토큰 × 다음 압축까지 실린 응답 수(압축 뒤 다시 붙은 사본 포함) ÷ 입력 합"
              "(상한 — 같은 차례의 입력 포함). †는 압축을 반영하지 않은 옛 계산(이전 엔진이 보낸 행).",
              "- 이월 = Gate A 를 부르기 직전 문맥 − 첫 응답 문맥(2회차부터의 중앙값). 새 대화 어림 절감 = 회차마다 새 대화로"
              " 시작했다면 덜 실렸을 입력 ÷ 입력 합(가정: 회차 안에서 늘어나는 양은 같다, 회차 안에서 압축된 뒤로는 0).", "",
              "| 프로젝트 | 세션 | 응답 | 첫 응답 문맥 | 응답당 평균 | 최대 문맥 | 압축(자동/수동) | Gate A 회차 | 이월(중앙) | "
              "새 대화 어림 절감 | 스킬 적재(토큰) | 하네스 스킬 몫 | 출력 한도 중단 |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(sessions, key=lambda r: r["last"], reverse=True):
        c = r.get("context") or {}
        if not c.get("calls"):
            continue
        loads = ", ".join(f"{n} {'/'.join(str(j) for j in js)}" for n, js in sorted(c["skill_loads"].items())) or "—"
        new = "compactions" in c
        share = (f"{100 * c['harness_skill_tokens'] / c['input_total']:.0f}%" + ("" if new else "†")
                 if c["input_total"] else "—")
        if new:
            comp = f"{c['compactions']['auto']}/{c['compactions']['manual']}"
            later = c["carry"][1:]
            carry = int(statistics.median(later)) if later else "—"
            saving = f"{100 * c['fresh_saving'] / c['input_total']:.0f}%" if c["input_total"] else "—"
            cycles = c["cycles"]
        else:
            comp = cycles = carry = saving = "?"
        lines.append(f"| {r['project']} | `{r['session'][:8]}` | {c['calls']} | {c['first']} | "
                     f"{c['input_total'] // c['calls']} | {c['max']} | {comp} | {cycles} | {carry} | {saving} | "
                     f"{loads} | {share} | {c['max_tokens_stops']} |")
    accounted = [r for r in sorted(sessions, key=lambda r: r["last"], reverse=True)
                 if r.get("gates") and "sources" in (r.get("context") or {})]
    if accounted:
        lines += ["", "## 문맥 출처 (하네스 세션, 머문 글자 기준 — 어림)", "",
                  "- 글자 수 × 다음 압축까지 실린 응답 수의 비율. 시스템 프롬프트·도구 정의(첫 응답 문맥)는 빠진다.",
                  "- 이미지는 base64 를 글자로 세지 않고 장수와 머문 응답 수만 센다. 한글과 영문은 글자당 토큰이 달라 비율은 어림이다.", "",
                  "| 프로젝트 | 세션 | 상위 출처 | 이미지(장 / 머문 응답) |", "|---|---|---|---|"]
        total, total_img = collections.Counter(), collections.Counter()
        for r in accounted:
            c = r["context"]
            total.update(c["sources"])
            total_img.update(c.get("images") or {})
            lines.append(f"| {r['project']} | `{r['session'][:8]}` | {_top_sources(c['sources'])} | "
                         f"{c['images']['count']} / {c['images']['resident']} |")
        lines.append(f"| 합계 | | {_top_sources(total, 8)} | {total_img['count']} / {total_img['resident']} |")
        lines += ["", "## 스킬 다시 싣기 (하네스 스킬)", "",
                  "- 본문 전체가 다시 실린 방식. 같은 내용으로 Skill 도구를 다시 부르면 본문 대신 「already loaded」 한 줄이 붙는다.",
                  "- 겹친 적재 = 같은 스킬의 앞 사본이 아직 문맥에 있는데(그사이 압축 없음) 본문이 또 실린 것.", "",
                  "- 인자와 함께 실린 스킬 = Skill(인자 있음)으로 본문이 다시 실린 스킬과 횟수(상위 3). 인자를 주면 같은 스킬이라도 본문이 "
                  "통째로 다시 실린다.", "",
                  "| 프로젝트 | 세션 | 직접 입력 | Skill(인자 있음) | Skill(인자 없음) | 기타 | 겹친 적재(회 / 토큰) | already loaded | "
                  "Claude Code | 인자와 함께 실린 스킬 |", "|---|---|---|---|---|---|---|---|---|---|"]
        for r in accounted:
            rl = r["context"]["reloads"]
            versions = r.get("cc_versions") or []
            cc = versions[0] if len(versions) == 1 else (f"{versions[0]}~{versions[-1]}" if versions else "—")
            by = rl.get("by_skill")
            top = ("—" if by is None else ", ".join(f"{k} {v['args']}" for k, v in sorted(
                by.items(), key=lambda kv: -kv[1].get("args", 0))[:3] if v.get("args")) or "0")
            lines.append(f"| {r['project']} | `{r['session'][:8]}` | {rl['typed']} | {rl['args']} | {rl['tool']} | "
                         f"{rl['other']} | {rl['dup']} / {rl['dup_tokens']} | {rl['notes']} | {cc} | {top} |")
    timed = [r for r in sorted(sessions, key=lambda r: r["last"], reverse=True) if r.get("gates") and "edits" in r]
    if timed:
        lines += ["", "## 코드 편집 시점 (Gate A 승인 전 · 회차 밖)", "",
                  "- 코드 편집 = Write·Edit·MultiEdit·NotebookEdit 로 .md·.txt·.claude/ 밖의 파일을 바꾼 호출. Bash 로 쓴 편집은 세지 못한다(하한).",
                  "- 승인 = 「Gate A 승인」「계획대로 구현」「자율 레인 승인」「C~E 일괄」 입력 또는 다음 Gate 호출. 회차 밖 = 그 세션의 첫 Gate 전, "
                  "또는 Gate E 뒤(작은 수정을 Gate 없이 한 것일 수 있다 — 위반인지는 사람이 본다).", "",
                  "- 승인 전 편집은 프로젝트 안의 파일만 센다. 임시 스크립트처럼 프로젝트 밖 파일은 「그중 밖」 칸에 따로 센다(— 는 이 칸을 "
                  "모르는 옛 엔진의 행).", "",
                  "| 프로젝트 | 세션 | Gate A 회차 | 코드 편집 | 승인 전 편집(회차 수) | 회차 밖 편집 | 승인 전 프로젝트 밖 편집 |",
                  "|---|---|---|---|---|---|---|"]
        for r in timed:
            e = r["edits"]
            lines.append(f"| {r['project']} | `{r['session'][:8]}` | {r['gates'].split().count('a')} | {e['code']} | "
                         f"{e['pre_approval']} ({e['pre_approval_cycles']}) | {e['outside_cycle']} | "
                         f"{e.get('pre_approval_outside', '—')} |")
    lines += ["", "## Gate 순서 (세션별)", "", "| 프로젝트 | 세션 | 마지막 활동 | Gate | C 직후 E |", "|---|---|---|---|---|"]
    for r in sorted(sessions, key=lambda r: r["last"], reverse=True):
        if r["gates"]:
            lines.append(f"| {r['project']} | `{r['session'][:8]}` | {r['last'][:10]} | {r['gates']} | {r['c_to_e']} |")
    lines += ["", "## Gate B 질문 결과 (회차별 사람의 응답)", "",
              "- Gate 순서가 아니라 질문에 어떻게 응답했는지 본다. Skill·슬래시 호출 없이 진행한 회차는 빠진다(하한).",
              "- 「답함」은 글자만 본다 — 되묻기나 불만도 답으로 센다(상한). 답의 정오와 사람의 실제 이해는 재지 않는다.",
              "- 스킵 수 하나로 판단하지 않는다 — 낮아도 의례일 수 있고 높아도 정당할 수 있다. 계획 변경 칸은 gate-b Step 3 이 적기 시작한 뒤 회차부터 쌓인다.", "",
              "- 확인(진행) = 확인형 Gate B(2026-11-10~)에서 세 줄을 보고 「진행」으로 넘긴 회차. 그 자리에서 묻거나 계획을 바꾸면 「답함」이다.", "",
              "| 프로젝트 | 세션 | 마지막 활동 | 질문 없음 | 확인(진행) | 답함 | 일부 답 뒤 스킵 | 스킵 | 답 없음 | 계획 변경 있음/없음 |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    gate_b_cols = ("none", "confirmed", "answered", "partial", "skipped", "unanswered")
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
    reviewed = [r for r in sessions if r.get("fresh_review")]
    if reviewed:
        lines += ["", "## 새 문맥 검토 (Gate A, 시험 운영)", "",
                  "- 발동·강제·미실행·실패는 `fresh_review.py` 출력 첫 줄, 검토는 `[새 문맥 검토]` Agent 호출 수, 기록은 Gate A 블록에 쓴 줄이다.",
                  "- 발동했는데 기록이 없으면 건너뛴 회차다. 토큰·시간은 바로 끝난 호출은 결과에서, 뒤에서 돈 호출은 완료 알림에서 읽는다.", "",
                  "| 프로젝트 | 세션 | 발동 | 강제 | 미실행 | 실패 | 알 수 없음 | 검토 | 토큰(중앙) | 시간(중앙, 초) | 기록 |",
                  "|---|---|---|---|---|---|---|---|---|---|---|"]
        heads = []
        for r in sorted(reviewed, key=lambda r: r["last"], reverse=True):
            f = r["fresh_review"]
            tokens = int(statistics.median(f["tokens"])) if f.get("tokens") else "—"
            secs = int(statistics.median(f["ms"]) / 1000) if f.get("ms") else "—"
            # 검토가 돌았는데 기록이 없어도 건너뛴 회차다 — 발동 줄을 알아보지 못한 회차가 있었다(2026-11-10 노트북)
            rec = "; ".join(f.get("records") or []) or ("없음(건너뜀?)" if f.get("fired") or f.get("reviews") else "—")
            lines.append(f"| {r['project']} | `{r['session'][:8]}` | {f.get('fired', 0)} | {f.get('forced', 0)} | "
                         f"{f.get('not_run', 0)} | {f.get('failed', 0)} | {f.get('unknown', 0)} | {f.get('reviews', 0)} | "
                         f"{tokens} | {secs} | {rec} |")
            heads += [f"- `{r['session'][:8]}` 알 수 없음 첫 줄: {h}" for h in f.get("unknown_heads") or []]
        lines += ([""] + heads) if heads else []
    if progress is not None:
        lines += ["", "## DECISION_LOG 대기 예측의 진행", ""]
        if any("engine_at_start" in r for r in sessions):
            lines += ["- 갱신 시각이 기록된 PC 의 세션은 그 결정이 든 릴리스 뒤에 시작한 세션만 센다(기록 전에 시작한 세션은 버전을 몰라 세지 않는다). 나머지는 결정일 뒤 활동한 세션.", ""]
        lines += ["| 결정일 | 결정 | 지금 | 확인 시점 목표 | 자료 |", "|---|---|---|---|---|"]
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
    parser.add_argument("--sessions", action="append", default=[],
                        help="다른 컴퓨터에서 만든 sessions.jsonl 을 대화 기록 대신 읽는다(여러 번 줄 수 있다)")
    args = parser.parse_args(argv)
    out = args.out or os.path.join(os.path.expanduser("~/.claude/harness-reports"), datetime.date.today().isoformat())
    if args.sessions:
        data = load_sessions(args.sessions, since=args.since or None)
        source = "받은 세션 기록: " + ", ".join(args.sessions)
    else:
        data = collect(args.projects_dir, since=args.since or None, include_tmp=args.include_tmp)
        source = args.projects_dir
    decision_log = args.decision_log or os.path.join(os.path.dirname(HERE), "DECISION_LOG.md")
    changelog = os.path.join(os.path.dirname(os.path.abspath(decision_log)), "CHANGELOG.md")
    progress = (prediction_progress(decision_log, data["sessions"], changelog=changelog)
                if os.path.isfile(decision_log) else None)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "sessions.jsonl"), "w", encoding="utf-8") as f:
        for row in data["sessions"]:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with open(os.path.join(out, "report.md"), "w", encoding="utf-8") as f:
        f.write(render(data, progress, source, args.since))
    print(f"보고서: {os.path.join(out, 'report.md')} (세션 {len(data['sessions'])}개)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
