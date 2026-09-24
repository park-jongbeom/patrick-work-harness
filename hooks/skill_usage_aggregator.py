#!/usr/bin/env python3
"""Claude Code transcript JSONL에서 슬래시명령(Skill) 호출 횟수를 집계한다.

HARNESS-SELF-AUDIT-1 (2026-05-28) — 자가 진단 §4-2 + §6 명세.
9스킬(gate-a~e + audit + doc-cleanup + error-log + export-roles)의 30일 윈도우
+ 누적 호출 횟수를 프로젝트별로 집계하여 dashboard md를 생성한다.

HARNESS-SKILL-ANALYTICS-1 (2026-06-09) — 2가지 갭 보완:
  (a) 마커 소스 확대 — `commandName`만 보던 것을 Skill tool_use(`name:Skill`,
      `input.skill`)까지 포착. Skill tool_use가 commandName 상위집합이며,
      동일 호출은 id(tool_use id == commandName tool_use_id) 키로 union·dedup해
      이중카운트를 막는다. (error-log·export-roles는 양쪽 모두 진짜 0회=미사용.)
  (b) "언제" 차원 — 시간대(KST) 분포(§6) + 세션별 Gate 시퀀스(§7) 가시화.

표준 라이브러리만 사용 (json·pathlib·argparse·datetime·collections·sys).
외부 패키지 의존 없음.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 배포본이 싣는 스킬 9종 (2026-09-24 실측으로 맞춤).
# 원본 목록에 있던 error-log·export-roles 는 이 배포본에 없고,
# 대신 harness-update·init 이 있다.
NINE_SKILLS = [
    "gate-a", "gate-b", "gate-c", "gate-d", "gate-e",
    "audit", "doc-cleanup", "harness-update", "init",
]

# 배포본 일반화 (2026-09-24, HARNESS-ANALYTICS-PORT-1): 원본은 사설 절대경로였다.
# Claude Code 의 transcript 는 어느 OS 에서든 홈 밑 `.claude/projects` 에 쌓인다.
DEFAULT_PROJECTS_DIR = Path.home() / ".claude" / "projects"

# "언제" 차원 출력은 사용자(한국) 기준 시간대로 환산한다 (transcript ts는 UTC).
# 기본은 KST(+9). 다른 지역에서 쓸 때는 HARNESS_TZ_OFFSET 로 시간 오프셋을 준다.
_TZ_OFFSET = int(os.environ.get("HARNESS_TZ_OFFSET", "9"))
KST = timezone(timedelta(hours=_TZ_OFFSET))

# §7 Gate 시퀀스 표에 노출할 상위 시퀀스 개수.
TOP_SEQUENCES = 12


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--month", default=None,
                        help="대상 월 (YYYY-MM 형식, 기본=현재월)")
    parser.add_argument("--output", default=None,
                        help="출력 파일 경로 (기본=stdout)")
    parser.add_argument("--window-days", type=int, default=30,
                        help="윈도우 일수 (기본=30)")
    parser.add_argument("--projects-dir", type=Path, default=DEFAULT_PROJECTS_DIR,
                        help="Claude Code projects 디렉토리 경로")
    return parser.parse_args()


def _parse_ts(ts_raw):
    """ISO timestamp 문자열을 aware datetime으로. 실패 시 None."""
    if not ts_raw:
        return None
    try:
        return datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _collect_invocation(entry: dict, invocations: dict) -> None:
    """단일 JSONL 엔트리에서 스킬 호출 마커를 추출해 invocations(id→...)에 병합.

    두 소스를 id 키로 union한다 (동일 파일 = 동일 세션이므로 파일 단위 dedup 충분):
      - Skill tool_use (assistant): name=Skill·input.skill → authoritative, 항상 덮어씀
      - commandName 결과 (user): toolUseResult.commandName → setdefault 폴백
    Skill tool_use(invocation 시점)와 commandName 결과(약간 뒤)는 같은 id로 묶여
    Skill 쪽 (skill, ts)이 우선된다.
    """
    ts = _parse_ts(entry.get("timestamp"))
    if ts is None:
        return
    session_id = entry.get("sessionId")
    msg = entry.get("message")
    content = msg.get("content") if isinstance(msg, dict) else None

    # 소스 1: Skill tool_use (상위집합, authoritative)
    if isinstance(content, list):
        for block in content:
            if (isinstance(block, dict) and block.get("type") == "tool_use"
                    and block.get("name") == "Skill"):
                inp = block.get("input") or {}
                skill = inp.get("skill")
                tool_id = block.get("id")
                if skill and tool_id:
                    invocations[tool_id] = (skill, ts, session_id)

    # 소스 2: commandName 결과 (Skill 마커 없는 호출만 — 방어 폴백)
    tool_result = entry.get("toolUseResult")
    if isinstance(tool_result, dict):
        command_name = tool_result.get("commandName")
        if command_name:
            tool_id = None
            if isinstance(content, list):
                for block in content:
                    if (isinstance(block, dict)
                            and block.get("type") == "tool_result"):
                        tool_id = block.get("tool_use_id")
                        break
            if tool_id is None:  # id 부재 시 합성 키 (매우 드묾)
                tool_id = entry.get("uuid") or f"cmd:{command_name}:{ts.isoformat()}"
            invocations.setdefault(tool_id, (command_name, ts, session_id))


def iter_skill_invocations(projects_dir: Path):
    """모든 JSONL을 순회하며 스킬 호출을 (project, skill, ts, session_id)로 yield.

    Skill tool_use + commandName 두 마커 소스를 파일 단위 id 키로 union·dedup한다
    (HARNESS-SKILL-ANALYTICS-1). 이전 commandName 단독 집계 대비 Skill tool로만
    호출된 케이스(예: deep-research)를 추가 포착한다.
    """
    for project_dir in sorted(projects_dir.iterdir()):
        if not project_dir.is_dir():
            continue
        project_name = project_dir.name.lstrip("-").replace("media-ubuntu-data120g-", "")
        for jsonl_path in sorted(project_dir.glob("*.jsonl")):
            invocations: dict = {}  # tool_use_id → (skill, ts, session_id)
            try:
                with jsonl_path.open("r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(entry, dict):
                            _collect_invocation(entry, invocations)
            except OSError:
                continue
            for skill, ts, session_id in invocations.values():
                yield project_name, skill, ts, session_id


def build_session_sequences(session_events: dict) -> Counter:
    """sessionId → [(ts, skill)...] 를 ts 정렬 후 시퀀스 문자열 Counter로 환산."""
    sequences: Counter = Counter()
    for events in session_events.values():
        ordered = [skill for _, skill in sorted(events, key=lambda e: e[0])]
        if ordered:
            sequences["→".join(ordered)] += 1
    return sequences


# §8 이상 시퀀스 출력에 노출할 예시 시퀀스 개수.
TOP_ANOMALY_EXAMPLES = 5


def detect_anomalies(session_sequences: Counter) -> dict:
    """세션 Gate 시퀀스를 **인접 신호 기반**으로 분류해 이상 패턴을 집계한다.

    정본 흐름은 `gate-a→gate-b→gate-c→gate-e`(단순) / `…→gate-d→gate-e`(복잡).
    인접쌍 검사라 다트랙 반복(`a→b→c→e→a→b→c→e`)에 robust하다.

    이상 3종:
      - 검증 누락: `gate-b` 직후 `gate-c` 없이 `gate-e` (b→e) — Gate C 스킵 의심
      - 게이트 스킵: `gate-a` 직후 `gate-e` (a→e) — 구현·검증 동시 스킵
      - 계획 후 미진행: 시퀀스가 `gate-a` 단독 — 계획 적체
    정상으로 제외: gate-d 부재 · `b→c→e`(이전 세션 계획) · `a→audit` 등.
    """
    anomalies = {
        "verify_skipped": {"sessions": 0, "examples": []},  # b→e
        "gate_skipped": {"sessions": 0, "examples": []},    # a→e
        "plan_only": {"sessions": 0, "examples": []},       # 단독 a
    }
    for seq_str, count in session_sequences.items():
        seq = seq_str.split("→")
        pairs = list(zip(seq, seq[1:]))
        if seq == ["gate-a"]:
            _bump(anomalies["plan_only"], seq_str, count)
        if ("gate-b", "gate-e") in pairs:
            _bump(anomalies["verify_skipped"], seq_str, count)
        if ("gate-a", "gate-e") in pairs:
            _bump(anomalies["gate_skipped"], seq_str, count)
    return anomalies


def _bump(bucket: dict, seq_str: str, count: int) -> None:
    """이상 버킷의 세션 수를 누적하고 예시 시퀀스를 상한까지 보존."""
    bucket["sessions"] += count
    if len(bucket["examples"]) < TOP_ANOMALY_EXAMPLES:
        bucket["examples"].append(f"{seq_str} ({count})")


def build_recommendations(result: dict) -> list:
    """§4 저빈도/§6 피크/§8 이상을 종합해 최적화 권고를 1줄씩 생성한다."""
    recs: list = []
    anomalies = result.get("anomalies", {})
    vs = anomalies.get("verify_skipped", {}).get("sessions", 0)
    gs = anomalies.get("gate_skipped", {}).get("sessions", 0)
    po = anomalies.get("plan_only", {}).get("sessions", 0)
    if vs:
        recs.append(f"검증 누락 {vs}세션 (`gate-b→gate-e`) — Gate C 스킵 점검 권장")
    if gs:
        recs.append(f"게이트 스킵 {gs}세션 (`gate-a→gate-e`) — 비표준 흐름 검토")
    if po:
        recs.append(f"계획 후 미진행 {po}세션 (`gate-a` 단독) — 계획 적체 점검")
    zero_total = [s for s in NINE_SKILLS if result["total_by_skill"].get(s, 0) == 0]
    if zero_total:
        recs.append(f"0회 누적 스킬 {', '.join(f'`{s}`' for s in zero_total)} — 통합·폐기 검토 (§4 연계)")
    hour_counter = result.get("hour_counter", {})
    if hour_counter:
        peak_hour = max(hour_counter.items(), key=lambda kv: kv[1])[0]
        recs.append(f"피크 시간대 {peak_hour:02d}시 — 집중 작업대 활용")
    if not recs:
        recs.append("특이 패턴 없음 — 표준 흐름 유지")
    return recs


def aggregate(projects_dir: Path, window_start: datetime):
    """전체 집계 + 30일 윈도우 집계 + "언제" 차원(시간대·세션 시퀀스)을 반환."""
    total_by_project_skill: dict[tuple[str, str], int] = Counter()
    window_by_project_skill: dict[tuple[str, str], int] = Counter()
    total_by_skill: dict[str, int] = Counter()
    window_by_skill: dict[str, int] = Counter()
    other_commands: dict[str, int] = Counter()
    hour_counter: dict[int, int] = Counter()       # (b) 시간대(KST) 분포 — 9스킬
    session_events: dict[str, list] = defaultdict(list)  # (b) sessionId→[(ts,skill)]
    projects_seen: set[str] = set()
    transcript_count = 0
    event_count = 0

    for project_name, command_name, ts, session_id in iter_skill_invocations(projects_dir):
        projects_seen.add(project_name)
        event_count += 1
        if command_name in NINE_SKILLS:
            total_by_project_skill[(project_name, command_name)] += 1
            total_by_skill[command_name] += 1
            hour_counter[ts.astimezone(KST).hour] += 1
            if session_id:
                session_events[session_id].append((ts, command_name))
            if ts >= window_start:
                window_by_project_skill[(project_name, command_name)] += 1
                window_by_skill[command_name] += 1
        else:
            other_commands[command_name] += 1

    for project_dir in projects_dir.iterdir():
        if project_dir.is_dir():
            transcript_count += len(list(project_dir.glob("*.jsonl")))

    result = {
        "total_by_project_skill": total_by_project_skill,
        "window_by_project_skill": window_by_project_skill,
        "total_by_skill": total_by_skill,
        "window_by_skill": window_by_skill,
        "other_commands": other_commands,
        "hour_counter": hour_counter,
        "session_sequences": build_session_sequences(session_events),
        "session_count": len(session_events),
        "projects": sorted(projects_seen),
        "transcript_count": transcript_count,
        "event_count": event_count,
    }
    # §8 인사이트 — 이상 시퀀스 탐지 + 종합 최적화 권고 (HARNESS-SKILL-ANALYTICS-2)
    result["anomalies"] = detect_anomalies(result["session_sequences"])
    result["recommendations"] = build_recommendations(result)
    return result


def format_dashboard(result: dict, month: str, window_start: datetime, window_end: datetime) -> str:
    lines: list[str] = []
    lines.append(f"# 슬래시명령(Skill) 사용률 대시보드 — {month}")
    lines.append("")
    lines.append(f"> **생성일**: {window_end.strftime('%Y-%m-%d')}")
    lines.append(f"> **생성 스크립트**: `{Path(__file__).name}` ({Path(__file__).parent.name}/)")
    lines.append(f"> **30일 윈도우**: {window_start.strftime('%Y-%m-%d')} ~ {window_end.strftime('%Y-%m-%d')}")
    lines.append(f"> **데이터 범위**: `{DEFAULT_PROJECTS_DIR}` (프로젝트 {len(result['projects'])}개 · JSONL {result['transcript_count']}개 · 슬래시명령 이벤트 {result['event_count']}건)")
    lines.append(f"> **트리거**: HARNESS-SELF-AUDIT-1 (자가 진단 §4-2 + §6 명세)")
    lines.append("")
    lines.append("## 1. 9스킬 호출 횟수 (전체 프로젝트 합산)")
    lines.append("")
    lines.append("| 스킬 | 30일 윈도우 | 누적 | 비고 |")
    lines.append("|------|------------|------|------|")
    for skill in NINE_SKILLS:
        window = result["window_by_skill"].get(skill, 0)
        total = result["total_by_skill"].get(skill, 0)
        note = ""
        if total == 0:
            note = "**0회 누적 — 통합·폐기 후보**"
        elif window == 0 and total > 0:
            note = "30일 0회 (저빈도 — 통합 후보)"
        elif total < 5:
            note = "누적 < 5 (검토 후보)"
        lines.append(f"| `{skill}` | {window} | {total} | {note} |")
    lines.append("")
    lines.append("## 2. 9스킬 × 프로젝트별 누적")
    lines.append("")
    header = "| 프로젝트 | " + " | ".join(f"`{s}`" for s in NINE_SKILLS) + " |"
    separator = "|" + "---|" * (len(NINE_SKILLS) + 1)
    lines.append(header)
    lines.append(separator)
    for project in result["projects"]:
        cells = []
        for skill in NINE_SKILLS:
            count = result["total_by_project_skill"].get((project, skill), 0)
            cells.append(str(count) if count > 0 else "·")
        lines.append(f"| {project} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("## 3. 30일 윈도우 (저빈도 식별)")
    lines.append("")
    lines.append(header)
    lines.append(separator)
    for project in result["projects"]:
        cells = []
        for skill in NINE_SKILLS:
            count = result["window_by_project_skill"].get((project, skill), 0)
            cells.append(str(count) if count > 0 else "·")
        lines.append(f"| {project} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("## 4. 통합·폐기 후보 식별 (§5 인계 권고)")
    lines.append("")
    zero_total = [s for s in NINE_SKILLS if result["total_by_skill"].get(s, 0) == 0]
    low_total = [s for s in NINE_SKILLS if 0 < result["total_by_skill"].get(s, 0) < 5]
    zero_window = [s for s in NINE_SKILLS
                   if result["total_by_skill"].get(s, 0) > 0
                   and result["window_by_skill"].get(s, 0) == 0]
    if zero_total:
        lines.append(f"- **0회 누적 (Skill tool 호출 marker 미발견)**: {', '.join(f'`{s}`' for s in zero_total)}")
        lines.append("  - 사용자 명시 호출 또는 hook 우회 경로로 사용 중일 가능성 잔존 (별도 검증 필요)")
        lines.append("  - 통합·폐기 후보 → §5 「조건부」 인계")
    if low_total:
        lines.append(f"- **누적 < 5회 (저빈도)**: {', '.join(f'`{s}`' for s in low_total)}")
        lines.append("  - 통합·문서 회수 검토 후보 (예: 단일 hook으로 흡수 가능 여부)")
    if zero_window:
        lines.append(f"- **30일 0회 (최근 미사용)**: {', '.join(f'`{s}`' for s in zero_window)}")
    if not (zero_total or low_total or zero_window):
        lines.append("- 9스킬 모두 활성 (통합·폐기 후보 없음)")
    lines.append("")
    lines.append("## 5. 기타 호출 (9스킬 외 — 참고)")
    lines.append("")
    if result["other_commands"]:
        lines.append("| 호출명 | 누적 |")
        lines.append("|--------|------|")
        for name, count in result["other_commands"].most_common():
            lines.append(f"| `{name}` | {count} |")
    else:
        lines.append("_(없음)_")
    lines.append("")
    lines.append("## 6. 시간대 분포 (KST — 9스킬 호출, 「언제」)")
    lines.append("")
    hour_counter = result["hour_counter"]
    if hour_counter:
        lines.append("| 시각(KST) | 호출 수 |")
        lines.append("|-----------|---------|")
        for hour in range(24):
            count = hour_counter.get(hour, 0)
            if count:
                lines.append(f"| {hour:02d}시 | {count} |")
        peak_hour, peak_count = max(hour_counter.items(), key=lambda kv: kv[1])
        lines.append("")
        lines.append(f"> 피크 시간대: {peak_hour:02d}시 ({peak_count}회)")
    else:
        lines.append("_(데이터 없음)_")
    lines.append("")
    lines.append("## 7. Gate 시퀀스 (세션별 흐름, 「언제」)")
    lines.append("")
    sequences = result["session_sequences"]
    if sequences:
        lines.append(f"> 세션 {result['session_count']}개 · 고유 시퀀스 {len(sequences)}종 "
                     f"(상위 {min(TOP_SEQUENCES, len(sequences))} 표시)")
        lines.append("")
        lines.append("| 세션 수 | Gate 시퀀스 |")
        lines.append("|---------|-------------|")
        for seq, count in sequences.most_common(TOP_SEQUENCES):
            lines.append(f"| {count} | `{seq}` |")
    else:
        lines.append("_(데이터 없음)_")
    lines.append("")
    lines.append("## 8. 사용 패턴 인사이트 (이상 시퀀스·최적화 권고, 「분석」)")
    lines.append("")
    lines.append("> 정본 흐름 `gate-a→gate-b→gate-c→gate-e`(단순)/`…→gate-d→gate-e`(복잡) 대비 인접 신호 기반 이상 탐지 (다트랙 반복 robust).")
    lines.append("")
    anomalies = result["anomalies"]
    anomaly_specs = [
        ("verify_skipped", "검증 누락 (`gate-b→gate-e` — Gate C 스킵 의심)"),
        ("gate_skipped", "게이트 스킵 (`gate-a→gate-e` — 구현·검증 동시 스킵)"),
        ("plan_only", "계획 후 미진행 (`gate-a` 단독 — 계획 적체)"),
    ]
    any_anomaly = any(anomalies[k]["sessions"] for k, _ in anomaly_specs)
    if any_anomaly:
        lines.append("| 이상 유형 | 세션 수 | 예시 시퀀스 |")
        lines.append("|-----------|---------|-------------|")
        for key, label in anomaly_specs:
            bucket = anomalies[key]
            if bucket["sessions"]:
                examples = ", ".join(f"`{e}`" for e in bucket["examples"])
                lines.append(f"| {label} | {bucket['sessions']} | {examples} |")
    else:
        lines.append("- 이상 패턴 없음 (전 세션 정본 흐름 정합)")
    lines.append("")
    lines.append("### 최적화 권고")
    lines.append("")
    for rec in result["recommendations"]:
        lines.append(f"- {rec}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    if args.month:
        target_month = datetime.strptime(args.month, "%Y-%m").replace(tzinfo=timezone.utc)
        if target_month.month == 12:
            window_end = target_month.replace(year=target_month.year + 1, month=1) - timedelta(seconds=1)
        else:
            window_end = target_month.replace(month=target_month.month + 1) - timedelta(seconds=1)
    else:
        window_end = datetime.now(timezone.utc)
    window_start = window_end - timedelta(days=args.window_days)

    if not args.projects_dir.exists():
        print(f"projects 디렉토리 없음: {args.projects_dir}", file=sys.stderr)
        return 1

    result = aggregate(args.projects_dir, window_start)
    month_label = args.month or window_end.strftime("%Y-%m")
    dashboard = format_dashboard(result, month_label, window_start, window_end)

    if args.output:
        # 🔴 HARNESS-ANALYTICS-PORT-2 (2026-09-25): 부모 디렉터리를 만든다.
        #
        # 종전에는 `write_text` 만 했고, 출력 경로의 부모가 없으면
        # `FileNotFoundError` 로 죽었다. 호출자인 `skill-usage-auto` 훅은
        # 예외를 stderr 로만 남기고 **항상 exit 0** 이라, 새 프로젝트에서는
        # 집계가 **매번 실패하면서 아무도 모르는** 상태가 된다(실측).
        #
        # 시험이 이걸 못 잡은 이유: 전부 `tempfile.mkdtemp()` 로 **이미 있는**
        # 디렉터리에 썼다. 실제 상황(디렉터리 없음)을 한 번도 재현하지 않았다.
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(dashboard, encoding="utf-8")
        print(f"dashboard 작성: {args.output}", file=sys.stderr)
    else:
        print(dashboard)
    return 0


if __name__ == "__main__":
    sys.exit(main())
