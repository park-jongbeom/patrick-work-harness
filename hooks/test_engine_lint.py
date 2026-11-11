#!/usr/bin/env python3
"""엔진 배포 파일 일관성 린트 (HARNESS-LINT-1, 2026-10-21).

배포되는 파일(skills/ 전체, hooks/ 의 시험 아닌 파일)에서 아래 결함을 결정적으로 잡는다.
같은 결함이 문구 수정으로 세 번 되풀이됐기 때문에 글이 아니라 시험으로 묶는다
(Gate 역할 표기 3회, 제품명 잔존 반복 — 하네스 개선 Harness2 도입 검증 보고서).

  1. 소스 저장소 전용 이름 — 목록은 커밋하지 않는 `sync-from-source.local` 의 `name` 줄에서 읽고 추적 중인 모든 파일을 본다
     (공개 저장소에 이름을 적지 않는다, 2026-11-05). 목록이 없는 곳(깨끗한 컨테이너)에서는 건너뛴다 — 이름은 동기화로만
     들어오고, 동기화와 릴리스 전 시험은 목록이 있는 작업 서버에서 돈다.
  2. 은퇴한 스킬 참조 — /error-log · /doc-update · /export-roles.
  3. 어떤 설치 경로도 만들지 않는 파일 참조 — HARNESS_EVOLUTION_LOG.
  4. 프로젝트에 있을 수도 없을 수도 있는 파일(CLAUDE_DETAIL.md) 은 「없으면 건너뛴다」는
     단서와 함께만 언급한다.
  5. 소스 쪽 저장소 수를 박은 표현 — 「세 저장소」「three repositories」.
  6. 훅이 발동 표지로 읽는 문자열(self-debug N회 · FIX-B N건)을 쓰라고 지시하는 스킬이 있다.
  7. 스킬이 `${CLAUDE_SKILL_DIR}/<파일>` 로 부르는 파일이 실제로 같이 배포된다.
  8. 일괄 실행 문구(「C~E 일괄」「D~E 일괄」)가 쓰이면 gate-c 에 그 정의 절이 있다 (S4, 2026-10-22).
  9. 정의되지 않은 일괄 문구(예: 「B~E 일괄」)를 쓰지 않는다.
 10. Gate D 를 선택 단계처럼 표시하지 않는다 — `(/gate-d)`, 「Gate C or Gate D」. D 는 생략 불가(2026-10-22 결정).
 11. Gate 스킬이 dashboard-sync 배선을 말하면 `hooks/hooks.json` 의 실제 이벤트를 함께 말한다 (S5a, 2026-10-22 —
     「항상 Stop 첫 항목」이라 적었지만 플러그인·install.sh 는 PostToolUse 에 배선한다). /init·/harness-update 는
     자기 배선(Stop)을 설명하므로 제외.
 12. 한 스킬 안에 같은 코드 블록(3줄 이상)이 두 번 나오지 않는다.
 13. 스킬이 주는 CURRENT_SESSION 틀은 훅이 읽는 한글 라벨(`**세션 ID**`·`**현재 상태**`)을 쓰고 영문 라벨을 쓰지 않는다
     (S5b, 2026-10-22 — /init 틀이 영문이라 그 틀대로 쓴 문서는 가드·대시보드가 세션을 못 찾았다).
 14. `/gate-x ← 역할` 표기는 현행 역할(A 계획·B 이해도·C 구현·D 검증·E 기록)과 맞는다 (S5b — README 사용법이 B=구현 옛 체계였다).
 15. gate-a 의 `### 레인 판정` 예시는 `parse_lane_decision` 이 「자율」로 읽는다 (S6, 2026-10-22 — 레인 범위 훅이 이 파서로
     계획을 읽으므로, 스킬이 가르치는 형식과 파서가 어긋나면 자율 레인이 아무 말 없이 영영 열리지 않거나 잘못 열린다).
 16. 「자율 레인 승인」을 말하는 스킬이 있으면 gate-c 에 그 절차 절(`## Autonomous lane (자율 레인)`)이 있다 (S8c).
 17. `hooks/hooks.json` 에 배선된 훅은 README 훅 표(영문·한글)에 모두 있고, 종류 칸의 이벤트가 실제 배선과 같다 (S8c —
     표에 훅 3개가 빠져 있었고 dashboard-sync 를 Stop 이라 적었다. S5a 는 스킬 문구만 고쳐 README 를 놓쳤다).
 18. 스킬이 `${CLAUDE_PLUGIN_ROOT}/hooks/<파일>`·`${CLAUDE_PLUGIN_ROOT}/plugin.json` 으로 부르는 파일이 실제로 있다 (A1, 2026-10-22 —
     install.sh 가 이 경로를 훅 설치 폴더로 바꿔 쓰므로, 이름이 바뀌면 플러그인·install.sh 설치가 함께 깨진다).
 19. 스킬이 보여 주는 settings.json 훅 예시(`"command": …`)에 `${CLAUDE_PLUGIN_ROOT}` 를 쓰지 않는다 (A2, 2026-10-22 — Claude Code 는
     settings.json 의 훅에서 이 변수를 거부한다: 「only available in hooks defined in a plugin's hooks/hooks.json file」. `/init` 이
     그렇게 배선한 훅은 한 번도 돌지 않고 응답마다 훅 오류만 남겼다).

 20. gate-b 는 스킵을 증거로 쓰지 않는다 — Step 1 은 스킵 행을 No record 로 보고, Step 4 는 행을 남기지 않는다 (2026-11-05 — 스킵 행이
     26분 뒤 「유효」로 읽혀 큰 폭발반경 변경이 질문 없이 통과했다).
 21. gate-b 의 근거 문구는 독자가 따라갈 수 있고 효과를 부풀리지 않는다 — 없는 내부 노트를 가리키거나, 계획을 펴 둔 질문을 인출 연습이라고
     말하지 않는다 (2026-11-05).

 22. Gate B 의 발동 판정은 스크립트가 낸다 — gate-a·gate-b 가 `gate_b_trigger.py` 를 부르고, 옛 3단계 위험 분류를 쓰지 않는다 (2026-11-05 —
     표에 migration 이 있어도 모델이 운영 마이그레이션을 「일반」으로 판정했다).

 23. 은퇴한 훅은 돌아오지 않는다 — 파일·hooks.json·NEW_HOOKS 에 없고, install.sh 가 남은 배선을 지우고, sync-from-source.sh 가 원본에서 다시 들여오지
     않고, /harness-update 가 프로젝트 배선을 지운다 (2026-11-05). 스킬은 은퇴한 훅을 쓰는 것처럼 말하지 않는다.

 24. 스킬은 `git restore .` 를 지시하지 않는다 — Gate C 의 구현은 커밋 전이라 함께 사라진다 (2026-11-05).
 25. 프로젝트가 채우는 Build · Test 표는 /harness-update 가 덮어쓰는 HARNESS 구역 밖에 있고, 옛 구역의 표는 덮어쓰기 전에 옮긴다 (2026-11-05).
 26. 공개 스크립트에 작업 서버의 절대경로를 박지 않는다 — install.sh·sync-from-source.sh 는 배포되지 않아 규칙 2 가 보지 않는다 (2026-11-05).
 27. gate-b 는 미발동이면 멈추지 않고 gate-c 로 이어 간다. 미발동이 대부분이라 빈 정지가 회차마다 말 한마디를 쓴다 (2026-11-05).

 28. Gate 산출물은 대시보드 위쪽이 보이거나, 훅·파서가 읽거나, 다음 Gate 가 쓸 때만 둔다 — 읽는 곳 없다고 확인한 항목이 돌아오지 않는다 (2026-11-05, 사용자는
     대시보드 맨 위로 판단한다).
 29. Gate 스킬 다섯 개의 합이 예산을 넘지 않는다. 스킬 본문은 부를 때마다 문맥에 실린다 — 늘리려면 하나를 빼거나 SKILL_DETAIL 로 옮긴다 (2026-11-05).

 30. 스킬은 정의되지 않은 `${HARNESS_PLANS_DIR}` 를 쓰지 않고 `archive_path`·`worklog_path` 를 쓴다 — 실제 설정에서 두 값은 그 경로와 같았고,
     엔진 실행에서는 변수 해석이 갈려 아카이브가 한 단계 더 들어갔다 (2026-11-05).
 31. Gate E 는 아카이브 첫 줄에 `final_status:` 를 쓴다 — gate-a·doc-cleanup 이 읽는데 쓰는 지시가 없었고, doc-cleanup 은 인덱스의 ✅E 행을
     먼저 지워 이 필드가 마지막 근거다 (2026-11-05).
 32. gate-a 의 R/V/D 예시는 V 표와 맞는다 (2026-11-05).
 33. 배포 파이썬은 텍스트 파이프·파일을 열 때 인코딩을 적는다 — 적지 않으면 한국어 윈도에서 cp949 로 읽혀 한글에서 죽는다. 변조 가드가
     한국어 윈도 PC 의 한글 문서 프로젝트에서 10/22 부터 Stop 680회를 이렇게 실패해 검사가 통째로 빠졌다 (2026-11-06).
 34. install.sh 의 따옴표 없는 heredoc(변수를 펼치는 파이썬 블록) 안에는 백틱·`$(` 를 쓰지 않는다 — 주석이라도 bash 가 명령으로 실행한다.
     설치 때마다 주석 속 `python3 없는파일.py` 가 실제로 돌았다 (2026-11-06).
 35. README·ARCHITECTURE·PROJECT_MAP 은 Gate A 승인 전 편집을 도구가 막는다고 말하지 않는다 — 막는 훅은 2026-09 에 뺐고(오탐·Bash 우회)
     같은 README 의 설계 원칙이 「강제라고 말하면 안 된다」고 적었는데도 머리말 네 곳이 「막는다·일어나지 않는다」고 약속했다. 외부 평가가
     짚었다 (2026-11-10).
 36. PROJECT_MAP 이 가리키는 저장소 경로와 구조도의 이름은 실제로 있다 — 2026-07-20 에 뺀 `.github/workflows/` 를 CI 라고 적고 있었다
     (2026-11-10).
 37. 마무리 스킬(`/commit-up`)은 넓게 담지도 올리지도 않는다 — `git add -A`·`git add .`·`git commit -a`·`git push` 는 금지 문장으로만 나오고,
     doc-cleanup·audit 은 Skill 도구로 부른다(직접 입력한 명령은 스킬 본문을 회차마다 다시 싣는다). audit 문턱은 gate-e 와, 문서 임계값은
     doc-cleanup 과 같고, Gate E 의 끝 안내가 이 스킬을 가리킨다 (2026-11-11 — 실제 마무리 구간 15개에서 같은 입력을 회차마다 손으로 쳤고,
     「정리」로 한 일과 audit 을 건너뛴 사실의 표시가 매번 달랐다).
 38. `next_action` 을 쓰는 스킬(gate-e·commit-up)은 값을 통째로 바꾸고 끝난 항목을 빼라고 말한다 — 지시가 없어 끝난 항목이 이어 붙어
     실제 인덱스에서 1,000 바이트를 넘었고 대시보드 머리 칸이 화면 높이를 넘었다 (2026-11-11).

ENGINE_LINT_ROOT 로 다른 트리(예: `git archive` 로 푼 과거 커밋)를 검사할 수 있다.
"""
import ast
import collections
import json
import os
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(os.environ.get("ENGINE_LINT_ROOT") or pathlib.Path(__file__).resolve().parent.parent)
RETIRED_SKILLS = ("error-log", "doc-update", "export-roles")
NEVER_CREATED = ("HARNESS_EVOLUTION_LOG",)
OPTIONAL_PROJECT_FILES = ("CLAUDE_DETAIL.md",)
OPTIONAL_QUALIFIERS = ("skip", "N/A", "2>/dev/null", "if present", "if your project")


def shipped_files():
    files = sorted(p for p in (ROOT / "skills").rglob("*") if p.is_file() and p.suffix in (".md", ".py"))
    files += sorted(p for p in (ROOT / "hooks").glob("*") if p.is_file()
                    and p.suffix in (".py", ".json") and not p.name.startswith("test_"))
    return files


def lines_of(path):
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def hits(pattern, files=None):
    rx = re.compile(pattern)
    out = []
    for f in files or shipped_files():
        for i, line in enumerate(lines_of(f), 1):
            if rx.search(line):
                out.append(f"{f.relative_to(ROOT)}:{i}: {line.strip()[:120]}")
    return out


GATE_B = ROOT / "skills" / "gate-b" / "SKILL.md"
#: 규칙 35 — 승인 전 편집을 도구가 막는다는 주장. 부정문(「막지 않는다」「does not block」)은 걸리지 않게 동사를 좁혔다.
ENFORCEMENT_CLAIMS = (r"(?i)\bprevents?\b[^.\n]*before (?:a|the) plan is approved",
                      r"승인\s*전[^\n]*(?:차단합니다|막습니다|막는다)",
                      r"승인\s*전까지[^\n]*(?:일어나지|발생하지)\s*않",
                      r"(?i)\bno code (?:changes?|edits?)\b[^.\n]*\b(?:until|before)\b[^.\n]*approv")


def repo_names():
    """저장소 안의 파일·폴더 이름과 상대 경로(.git·__pycache__ 제외). git 이 없는 트리(ENGINE_LINT_ROOT)에서도 돈다."""
    names, paths = set(), set()
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
        rel = pathlib.Path(base).relative_to(ROOT)
        for n in dirs + files:
            names.add(n)
            paths.add((rel / n).as_posix())
    return names, paths
#: Gate A~E 본문 바이트 합의 상한. 2026-11-05 축소 뒤 값에 여유를 조금 둔 것이다.
GATE_SKILLS_BUDGET = 79_000
RETIRED_HOOKS = ("claude-gate-guard.py", "comprehension-ledger-stale-guard.py", "skill-usage-auto.py")
BATCH_DEFINITION_HEADING = "## Batch runs (C~E·D~E 일괄)"
DEFINED_BATCHES = {"C~E", "D~E"}
AUTONOMOUS_HEADING = "## Autonomous lane (자율 레인)"
HOOK_EVENTS = ("PreToolUse", "PostToolUse", "Stop", "UserPromptExpansion", "UserPromptSubmit", "SessionStart")
STUB_LABELS = ("> **세션 ID**:", "> **현재 상태**:")
ENGLISH_STUB_LABELS = r"\*\*Session ID\*\*|\*\*Status\*\*:|\|\s*(?:Current Gate|Gate Progress|Start Date)\s*\|"
GATE_ROLE_WORDS = {
    "a": ("plan", "계획"), "b": ("comprehen", "이해도"), "c": ("implement", "구현"),
    "d": ("verif", "test", "검증", "시험"), "e": ("record", "session wrap", "기록", "세션 정리"),
}


def skills_and_readme():
    return [p for p in (ROOT / "skills").rglob("SKILL.md")] + [ROOT / "README.md"]


PRIVATE_NAMES = ROOT / "sync-from-source.local"


def private_names_pattern():
    """`sync-from-source.local` 의 `name` 줄을 하나의 정규식으로. 파일이 없으면 None."""
    try:
        lines = PRIVATE_NAMES.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    names = [l.split(None, 1)[1].strip() for l in lines if l.startswith("name ") and l.split(None, 1)[1:]]
    return "|".join(names) or None


def tracked_files():
    import subprocess
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True).stdout.split("\n")
    return [ROOT / f for f in out if f and (ROOT / f).is_file()]


class EngineLint(unittest.TestCase):
    def test_no_source_repo_names_in_tracked_files(self):
        pattern = private_names_pattern()
        if not pattern:
            self.skipTest("sync-from-source.local 이 없다 — 원본 쪽 이름 검사는 작업 서버에서만 돈다")
        found = hits(pattern, files=tracked_files())
        self.assertEqual(found, [], "소스 저장소 전용 이름이 배포 파일에 남아 있음:\n" + "\n".join(found))

    def test_no_private_server_paths_in_tracked_files(self):
        """작업 서버의 디스크·계정 경로가 배포 파일에 박히지 않는다 (2026-10-29 대조 검증에서 집계기 코드에서 발견)."""
        # 배포 파일만이 아니라 공개되는 추적 파일 전체를 본다(2026-11-05 — CHANGELOG 에 남은 1줄을 놓쳤다).
        # 시험 파일은 일부러 가짜 계정 경로(`/home/u/…`)를 쓴다.
        files = [f for f in tracked_files() if not f.name.startswith("test_") and "fixtures" not in f.parts]
        found = hits(r"/(?:media|mnt|srv)/[\w.-]+/|/home/[\w.-]+(?![\w.-])|(?<![\w/])media-\w+-\w+", files=files)
        self.assertEqual(found, [], "작업 서버 경로가 배포 파일에 남아 있음:\n" + "\n".join(found))

    def test_no_retired_skill_references(self):
        found = hits(r"/(?:%s)\b" % "|".join(map(re.escape, RETIRED_SKILLS)))
        self.assertEqual(found, [], "은퇴한 스킬을 가리킴:\n" + "\n".join(found))

    def test_no_references_to_files_nothing_creates(self):
        found = hits("|".join(map(re.escape, NEVER_CREATED)))
        self.assertEqual(found, [], "어느 설치 경로도 만들지 않는 파일을 가리킴:\n" + "\n".join(found))

    def test_optional_project_files_are_qualified(self):
        bad = []
        for f in shipped_files():
            for i, line in enumerate(lines_of(f), 1):
                if any(name in line for name in OPTIONAL_PROJECT_FILES) and \
                        not any(q in line for q in OPTIONAL_QUALIFIERS):
                    bad.append(f"{f.relative_to(ROOT)}:{i}: {line.strip()[:120]}")
        self.assertEqual(bad, [], "없을 수도 있는 프로젝트 파일을 단서 없이 가리킴:\n" + "\n".join(bad))

    def test_no_hardcoded_repository_count(self):
        found = hits(r"세 저장소|3개 저장소|three repositories")
        self.assertEqual(found, [], "소스 쪽 저장소 수를 박은 표현:\n" + "\n".join(found))

    def test_guard_trigger_markers_are_instructed_by_a_skill(self):
        skills_text = "\n".join("\n".join(lines_of(p)) for p in (ROOT / "skills").rglob("SKILL.md"))
        for marker in ("self-debug N회", "FIX-B N건"):
            self.assertIn(marker, skills_text,
                          f"error-topics-guard 가 읽는 표지 「{marker}」를 쓰라고 지시하는 스킬이 없음")

    def test_skill_dir_references_exist(self):
        missing = []
        for skill_md in (ROOT / "skills").rglob("SKILL.md"):
            for i, line in enumerate(lines_of(skill_md), 1):
                for rel in re.findall(r"\$\{CLAUDE_SKILL_DIR\}/([\w./-]+)", line):
                    if not (skill_md.parent / rel).is_file():
                        missing.append(f"{skill_md.relative_to(ROOT)}:{i}: {rel}")
        self.assertEqual(missing, [], "스킬이 부르는 번들 파일이 없음:\n" + "\n".join(missing))

    def test_batch_phrases_have_a_definition(self):
        used = hits(r"[A-E]~E 일괄", files=skills_and_readme())
        if not used:
            return
        gate_c = (ROOT / "skills" / "gate-c" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn(BATCH_DEFINITION_HEADING, gate_c.splitlines(),
                      "일괄 문구가 쓰이는데 gate-c 에 정의 절이 없음:\n" + "\n".join(used))

    def test_no_undefined_batch_phrases(self):
        bad = [h for h in hits(r"[A-E]~E 일괄", files=skills_and_readme())
               if any(m not in DEFINED_BATCHES for m in re.findall(r"([A-E]~E) 일괄", h))]
        self.assertEqual(bad, [], "정의되지 않은 일괄 문구:\n" + "\n".join(bad))

    def test_gate_d_is_not_marked_optional(self):
        found = hits(r"\(/gate-d\)|Gate C or Gate D|Gate B → C → E", files=skills_and_readme())
        self.assertEqual(found, [], "Gate D 를 선택 단계처럼 표시함:\n" + "\n".join(found))

    def test_dashboard_sync_wiring_claims_match_hooks_json(self):
        cfg = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        events = {ev for ev, groups in cfg.get("hooks", {}).items()
                  for g in groups for h in g.get("hooks", []) if "session-dashboard-sync" in h.get("command", "")}
        self.assertTrue(events, "hooks.json 에 session-dashboard-sync 배선이 없음")
        bad = []
        for name in ("gate-a", "gate-b", "gate-c", "gate-d", "gate-e"):
            path = ROOT / "skills" / name / "SKILL.md"
            for i, line in enumerate(lines_of(path), 1):
                if "session-dashboard-sync" in line and ("Stop" in line or "PostToolUse" in line) \
                        and not all(ev in line for ev in events):
                    bad.append(f"{path.relative_to(ROOT)}:{i}: {line.strip()[:110]}")
        self.assertEqual(bad, [], f"hooks.json 배선({sorted(events)})과 다른 주장:\n" + "\n".join(bad))

    def test_no_duplicate_code_blocks_within_a_skill(self):
        dup = []
        for path in (ROOT / "skills").rglob("SKILL.md"):
            blocks = re.findall(r"```[^\n]*\n(.*?)```", path.read_text(encoding="utf-8"), re.S)
            counts = collections.Counter(b.strip() for b in blocks if b.strip().count("\n") >= 2)
            dup += [f"{path.relative_to(ROOT)}: {k.splitlines()[0][:60]!r} ×{v}" for k, v in counts.items() if v > 1]
        self.assertEqual(dup, [], "같은 코드 블록이 한 스킬에 두 번 이상:\n" + "\n".join(dup))

    def test_current_session_stubs_use_labels_hooks_parse(self):
        hooks_src = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "hooks").glob("*.py")
                              if not p.name.startswith("test_"))
        for label in STUB_LABELS:
            self.assertTrue(label[2:].replace("*", "\\*") in hooks_src, f"훅이 더는 {label} 를 읽지 않음 — 이 규칙을 고칠 것")
        bad = []
        for path in (ROOT / "skills").rglob("SKILL.md"):
            for block in re.findall(r"```[^\n]*\n(.*?)```", path.read_text(encoding="utf-8"), re.S):
                if "Session ID**" not in block and "세션 ID**:" not in block:
                    continue
                missing = [l for l in STUB_LABELS if l not in block]
                english = re.findall(ENGLISH_STUB_LABELS, block)
                if missing or english:
                    bad.append(f"{path.relative_to(ROOT)}: 빠진 라벨 {missing}, 영문 라벨 {english}")
        self.assertEqual(bad, [], "CURRENT_SESSION 틀이 훅이 읽는 라벨과 다름:\n" + "\n".join(bad))

    def test_gate_role_arrows_match_current_roles(self):
        bad = []
        for path in skills_and_readme():
            for i, line in enumerate(lines_of(path), 1):
                m = re.search(r"/gate-([a-e])\s*←\s*(.+)", line)
                if m and not m.group(2).lower().startswith(GATE_ROLE_WORDS[m.group(1)]):
                    bad.append(f"{path.relative_to(ROOT)}:{i}: {line.strip()[:100]}")
        self.assertEqual(bad, [], "Gate 역할 표기가 현행 체계(A 계획·B 이해도·C 구현·D 검증·E 기록)와 다름:\n" + "\n".join(bad))

    def test_gate_a_lane_example_parses_as_autonomous(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("sdp_lint", ROOT / "hooks" / "session_dashboard_parsers.py")
        sdp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sdp)
        detail = (ROOT / "skills" / "SKILL_DETAIL.md").read_text(encoding="utf-8")
        examples = [b for b in re.findall(r"```markdown\n(.*?)```", detail, re.S) if "### 레인 판정" in b]
        self.assertEqual(len(examples), 1, "SKILL_DETAIL 에 `### 레인 판정` 예시 블록이 정확히 하나 있어야 함")
        for label in sdp.LANE_LABELS:
            self.assertIn(f"- **{label}**:", examples[0], f"예시에 파서 라벨 「{label}」 이 없음")
        doc = "## Gate A 계획\n\n" + examples[0] + "\n### 변경 파일 (1개)\n\n1. `src/x.py` (수정)\n"
        d = sdp.parse_lane_decision(doc)
        self.assertEqual((d["lane"], d["reasons"]), ("자율", []), "gate-a 예시를 파서가 자율로 읽지 못함")

    def test_autonomous_lane_procedure_exists(self):
        used = hits(r"자율 레인 승인", files=list((ROOT / "skills").rglob("SKILL.md")))
        if not used:
            return
        gate_c = (ROOT / "skills" / "gate-c" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn(AUTONOMOUS_HEADING, gate_c.splitlines(),
                      "「자율 레인 승인」이 쓰이는데 gate-c 에 절차 절이 없음:\n" + "\n".join(used[:5]))

    def test_readme_hook_tables_match_hooks_json(self):
        cfg = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        wired = collections.defaultdict(set)
        for ev, groups in cfg.get("hooks", {}).items():
            for g in groups:
                for h in g.get("hooks", []):
                    wired[h.get("command", "").split("/")[-1].strip('"')].add(ev)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        bad = []
        for heading in ("### Hooks", "### 훅 목록"):
            section = readme.split(heading, 1)[1].split("\n#", 1)[0] if heading in readme else ""
            rows = {m.group(1): m.group(2) for m in re.finditer(r"^\| `([\w.-]+\.py)` \| ([^|]+) \|", section, re.M)}
            for name, events in sorted(wired.items()):
                if name not in rows:
                    bad.append(f"{heading}: {name} 행 없음")
                    continue
                claimed = {e for e in HOOK_EVENTS if e in rows[name]}
                if claimed != events:
                    bad.append(f"{heading}: {name} 종류 칸 {sorted(claimed)} ≠ 배선 {sorted(events)}")
        self.assertEqual(bad, [], "README 훅 표가 hooks.json 배선과 다름:\n" + "\n".join(bad))

    def test_plugin_root_references_exist(self):
        missing = []
        for skill_md in (ROOT / "skills").rglob("*.md"):
            for i, line in enumerate(lines_of(skill_md), 1):
                for rel in re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/((?:hooks/)?[\w.-]+\.(?:py|json))", line):
                    if not (ROOT / rel).is_file():
                        missing.append(f"{skill_md.relative_to(ROOT)}:{i}: {rel}")
        self.assertEqual(missing, [], "스킬이 부르는 하네스 파일이 없음:\n" + "\n".join(missing))

    def test_no_plugin_root_in_settings_snippets(self):
        # 값 안의 이스케이프된 따옴표(\\")를 건너뛴다 — 예시가 `python3 \\"${…}/hooks/x.py\\"` 꼴이다
        found = hits(r'"command":\s*"(?:[^"\\\n]|\\.)*\$\{CLAUDE_PLUGIN_ROOT\}', files=list((ROOT / "skills").rglob("*.md")))
        self.assertEqual(found, [], "settings.json 훅 예시에 ${CLAUDE_PLUGIN_ROOT} — Claude Code 가 실행을 거부한다:\n" + "\n".join(found))

    def test_gate_b_skip_is_not_evidence(self):
        text = GATE_B.read_text(encoding="utf-8")
        step1 = re.search(r"^## Step 1\..*?(?=^## )", text, re.S | re.M).group(0)
        step4 = re.search(r"^## Step 4\..*?(?=^## )", text, re.S | re.M).group(0)
        self.assertRegex(step1, r"미답 — 사용자 스킵.*\*\*No record\*\*", "Step 1 이 스킵 행을 증거에서 빼지 않음")
        self.assertRegex(step4, r"\*\*Skipped gate → no row", "Step 4 가 스킵의 기록 방식을 정하지 않음")

    def test_gate_b_basis_is_followable_and_not_overstated(self):
        found = hits(r"MIT 2025|internal research note|Dunlosky|[Ff]orce (?:actual )?retrieval|forced through", files=[GATE_B])
        self.assertEqual(found, [], "gate-b 근거 문구:\n" + "\n".join(found))

    def test_gate_b_verdict_comes_from_the_script(self):
        for name in ("gate-a", "gate-b"):
            text = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("gate_b_trigger.py", text, name + " 가 판정 스크립트를 부르지 않음")
        found = hits(r"Large blast radius|General risk|general risk or large|AI self-explains|폭발반경 大→|Pass after retry\s*/",
                     files=list((ROOT / "skills").rglob("*.md")))
        self.assertEqual(found, [], "옛 위험 분류:\n" + "\n".join(found))

    def test_retired_hooks_stay_retired(self):
        install = (ROOT / "install.sh").read_text(encoding="utf-8")
        sync = (ROOT / "sync-from-source.sh").read_text(encoding="utf-8")
        wired = (ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8")
        update = (ROOT / "skills" / "harness-update" / "SKILL.md").read_text(encoding="utf-8")
        listed = re.search(r"^RETIRED_HOOKS = \((.*?)\)", install, re.M | re.S)
        self.assertTrue(listed, "install.sh 에 은퇴 목록이 없음")
        for name in RETIRED_HOOKS:
            self.assertFalse((ROOT / "hooks" / name).exists(), name)
            self.assertNotIn(name, wired, name)
            self.assertNotIn("{hooks_dir}/" + name, install, name)
            self.assertIn(f'"{name}"', listed.group(1), name)
            self.assertIn(f'--exclude="{name}"', sync, name)
            self.assertIn(name, update, name)
        self.assertRegex(update, r"\| B \| \*\*Hook wiring.*retired hook", "Axis B 의 판정이 은퇴 훅을 보지 않으면 절차에 들어가지 않는다")

    def test_skills_do_not_talk_as_if_retired_mechanisms_run(self):
        skills = [f for f in (ROOT / "skills").rglob("*.md") if f.parent.name != "harness-update"]
        found = hits(r"comprehension-ledger-stale|skill-usage-auto|SM-2|double the previous", files=skills)
        self.assertEqual(found, [], "은퇴한 장치를 말함:\n" + "\n".join(found))

    def test_skills_do_not_order_a_destructive_restore(self):
        found = hits(r"git restore \.", files=list((ROOT / "skills").rglob("*.md")))
        self.assertEqual(found, [], "커밋 전 구현을 지우는 지시:\n" + "\n".join(found))

    def test_build_test_table_is_project_owned(self):
        init = (ROOT / "skills" / "init" / "SKILL.md").read_text(encoding="utf-8")
        zone = re.search(r"<!-- HARNESS:START v<_engine_version> -->(.*?)<!-- HARNESS:END -->", init, re.S).group(1)
        self.assertNotIn("Build · Test", zone, "HARNESS 구역 안이면 /harness-update 가 덮어쓴다")
        update = (ROOT / "skills" / "harness-update" / "SKILL.md").read_text(encoding="utf-8")
        axis_a = re.search(r"^### Axis A.*?(?=^### Axis B)", update, re.S | re.M).group(0)
        self.assertIn("Build · Test", axis_a, "옛 구역의 표를 옮기는 단계가 없음")

    def test_public_scripts_carry_no_server_paths(self):
        found = hits(r"/(?:media|mnt|srv)/\w[\w.-]*/\w", files=[ROOT / "install.sh", ROOT / "sync-from-source.sh"])
        self.assertEqual(found, [], "작업 서버 경로:\n" + "\n".join(found))

    def test_gate_b_pass_through_continues_to_gate_c(self):
        step5 = re.search(r"^## Step 5\..*?(?=^---)", GATE_B.read_text(encoding="utf-8"), re.S | re.M).group(0)
        self.assertRegex(step5, r"미발동.*invoke `/gate-c`", "미발동 회차가 멈춘다")

    def test_gate_outputs_without_a_reader_stay_out(self):
        gone = (r"OSS 카탈로그|0-OSS|External-dependency mapping|재사용 후보|refactor expectation|시스템 적합성 점검|"
                r"\| Effort \||Recommended-Model Computation|ReAct deliverable|session-dashboard\.html update")
        found = hits(gone, files=list((ROOT / "skills").rglob("*.md")))
        self.assertEqual(found, [], "읽는 곳 없는 산출물:\n" + "\n".join(found))

    def test_dashboard_top_inputs_stay_required(self):
        """사용자는 대시보드 맨 위로 판단한다 — 그 입력을 지시하는 문구가 사라지면 화면이 빈다."""
        gate_a = (ROOT / "skills" / "gate-a" / "SKILL.md").read_text(encoding="utf-8")
        for needle in ("**세션 주제**", "**작업 의도**", "### 이해 브리핑", "### 변경 파일", "### 실행 순서", "### 리스크 및 대응",
                       "### Gate A 범위 점검", "### Gate D 예상"):
            self.assertIn(needle, gate_a, needle)

    def test_gate_skills_stay_within_budget(self):
        total = sum((ROOT / "skills" / f"gate-{g}" / "SKILL.md").stat().st_size for g in "abcde")
        self.assertLessEqual(total, GATE_SKILLS_BUDGET, "Gate 스킬 본문이 예산을 넘었다 — 빼거나 SKILL_DETAIL 로 옮긴다")

    def test_skills_use_configured_doc_paths(self):
        found = hits(r"HARNESS_PLANS_DIR|plans/current_work/archive", files=list((ROOT / "skills").rglob("*.md")))
        self.assertEqual(found, [], "설정 대신 고정·미정의 경로:\n" + "\n".join(found))
        gate_e = (ROOT / "skills" / "gate-e" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("<archive_path>/ARCHIVE_", gate_e)
        self.assertIn("<worklog_path>/", gate_e)

    def test_gate_e_writes_the_status_line_others_read(self):
        readers = hits(r"\^final_status:|final_status: ✅", files=list((ROOT / "skills").rglob("*.md")))
        gate_e = (ROOT / "skills" / "gate-e" / "SKILL.md").read_text(encoding="utf-8")
        if readers:
            self.assertRegex(gate_e, r"first line[^\n]*`final_status: ✅E", "읽는 곳은 있는데 쓰는 지시가 없음")

    def test_rvd_examples_match_the_volume_table(self):
        gate_a = (ROOT / "skills" / "gate-a" / "SKILL.md").read_text(encoding="utf-8")
        for m in re.finditer(r"변경파일 (\d+) \+(\d)", gate_a):
            files, score = int(m.group(1)), int(m.group(2))
            self.assertEqual(score, 1 if files <= 3 else 2, m.group(0))

    def test_sync_script_reads_names_from_the_local_list(self):
        sync = (ROOT / "sync-from-source.sh").read_text(encoding="utf-8")
        self.assertIn("sync-from-source.local", sync)
        self.assertNotRegex(sync, r"REVIEW_HITS=\$\(grep -rlE '[^$]", "이름이 스크립트에 다시 박혔다")
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn("sync-from-source.local", ignored)

    def test_shipped_python_names_its_text_encoding(self):
        found = []
        for path in (p for p in shipped_files() if p.suffix == ".py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not isinstance(node, ast.Call):
                    continue
                kw = {k.arg: k.value for k in node.keywords}
                func = node.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                piped = name in ("run", "check_output", "Popen") and ("text" in kw or "universal_newlines" in kw)
                mode = node.args[1] if len(node.args) > 1 else kw.get("mode")
                opened = (isinstance(func, ast.Name) and name == "open"
                          and not (isinstance(mode, ast.Constant) and "b" in str(mode.value)))
                if (piped or opened) and "encoding" not in kw:
                    found.append(f"{path.relative_to(ROOT)}:{node.lineno} {name}")
        self.assertEqual(found, [], "인코딩 없이 연 텍스트 — 한국어 윈도에서 cp949 로 읽힌다:\n" + "\n".join(found))

    def test_docs_do_not_claim_the_tooling_blocks_early_edits(self):
        docs = [d for d in (ROOT / "README.md", ROOT / "ARCHITECTURE.md", ROOT / "PROJECT_MAP.md") if d.is_file()]
        found = [h for pattern in ENFORCEMENT_CLAIMS for h in hits(pattern, files=docs)]
        self.assertEqual(found, [], "승인 전 편집을 도구가 막는다는 주장 — 절차이지 사전 차단이 아니다:\n" + "\n".join(found))

    def test_project_map_points_at_files_that_exist(self):
        names, paths = repo_names()
        missing, in_tree = [], False
        for i, line in enumerate(lines_of(ROOT / "PROJECT_MAP.md"), 1):
            if line.startswith("```"):
                in_tree = not in_tree
                continue
            if in_tree:                                  # 구조도: `├── 이름/   # 설명`
                m = re.search(r"[├└]──\s+([^\s#]+)", line)
                if m and m.group(1).rstrip("/") not in names:
                    missing.append(f"PROJECT_MAP.md:{i}: {m.group(1)}")
                continue
            for token in re.findall(r"`([^`\s]+)`", line):
                if re.search(r"[~$<>*{}]|://", token):
                    continue
                path = token.rstrip("/").split(":")[0]
                if "/" in path:
                    ok = path in paths
                elif re.search(r"\.(?:py|md|json|sh)$", path):
                    ok = path in names
                else:
                    continue
                if not ok:
                    missing.append(f"PROJECT_MAP.md:{i}: {token}")
        self.assertEqual(missing, [], "PROJECT_MAP 이 없는 경로를 가리킨다:\n" + "\n".join(missing))

    def test_commit_up_stays_narrow_and_agrees_with_its_neighbours(self):
        text = (ROOT / "skills" / "commit-up" / "SKILL.md").read_text(encoding="utf-8")
        for needle in ("Never `git add -A`, `git add .` or `git commit -a`", "No `git push`", "through the Skill tool",
                       "stop and ask before any commit"):
            self.assertIn(needle, text, "마무리 스킬의 금지·호출 문장이 빠짐")
        wide = [ln.strip()[:100] for ln in text.splitlines()
                if re.search(r"git push|git add -A|git add \.(?!\w)|git commit -a", ln)
                and not re.search(r"\b(?:No|Never)\b", ln)]
        self.assertEqual(wide, [], "금지 문장 밖에서 넓은 담기·올리기를 말함:\n" + "\n".join(wide))

        def number(pattern, source, what):
            m = re.search(pattern, source)
            self.assertIsNotNone(m, f"{what} 을 찾지 못함")
            return m.group(1)

        gate_e = (ROOT / "skills" / "gate-e" / "SKILL.md").read_text(encoding="utf-8")
        cleanup = (ROOT / "skills" / "doc-cleanup" / "SKILL.md").read_text(encoding="utf-8")
        audit = r"`sessions_since_audit ≥ (\d+)`"
        self.assertEqual(number(audit, text, "commit-up 의 audit 문턱"), number(audit, gate_e, "gate-e 의 audit 문턱"),
                         "audit 문턱이 gate-e 와 다름")
        for var in ("CURRENT_SESSION_FILE", "SESSION_INDEX_FILE"):
            label = re.escape("`${" + var + "}`")
            self.assertEqual(number(label + r" over (\d+)", text, f"commit-up 의 {var} 임계값"),
                             number(label + r" \| (\d+) lines", cleanup, f"doc-cleanup 의 {var} 임계값"),
                             f"{var} 임계값이 doc-cleanup 과 다름")
        closing = gate_e[gate_e.index("mandatory final output"):]
        self.assertIn("/commit-up", closing, "Gate E 의 끝 안내가 마무리 스킬을 가리키지 않음")

    def test_next_action_writers_replace_instead_of_appending(self):
        for name in ("gate-e", "commit-up"):
            text = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
            line = next((ln for ln in text.splitlines() if "next_action" in ln and "Replace the whole value" in ln), None)
            self.assertIsNotNone(line, f"{name}: next_action 을 통째로 바꾸라는 지시가 없음")
            self.assertIn("drop finished items", line, f"{name}: 끝난 항목을 빼라는 지시가 없음")

    def test_install_heredocs_run_no_shell_inside(self):
        install = (ROOT / "install.sh").read_text(encoding="utf-8")
        found = []
        for m in re.finditer(r"<<(\w+)\n(.*?)\n\1\n", install, re.S):
            start = install.count("\n", 0, m.start()) + 2
            for i, line in enumerate(m.group(2).splitlines()):
                if "`" in line or "$(" in line:
                    found.append(f"install.sh:{start + i}: {line.strip()}")
        self.assertEqual(found, [], "따옴표 없는 heredoc 안의 셸 치환 — bash 가 실행한다:\n" + "\n".join(found))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    unittest.main(verbosity=2)
