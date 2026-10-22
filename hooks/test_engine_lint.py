#!/usr/bin/env python3
"""엔진 배포 파일 일관성 린트 (HARNESS-LINT-1, 2026-10-21).

배포되는 파일(skills/ 전체, hooks/ 의 시험 아닌 파일)에서 아래 결함을 결정적으로 잡는다.
같은 결함이 문구 수정으로 세 번 되풀이됐기 때문에 글이 아니라 시험으로 묶는다
(Gate 역할 표기 3회, 제품명 잔존 반복 — 하네스 개선 Harness2 도입 검증 보고서).

  1. 소스 저장소 전용 이름 — 패턴은 sync-from-source.sh 의 REVIEW_HITS 한 곳에서 읽는다
     (이 파일에 이름을 다시 적지 않는다).
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

ENGINE_LINT_ROOT 로 다른 트리(예: `git archive` 로 푼 과거 커밋)를 검사할 수 있다.
"""
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


def review_hits_pattern():
    text = (ROOT / "sync-from-source.sh").read_text(encoding="utf-8")
    m = re.search(r"REVIEW_HITS=\$\(grep -rlE '([^']+)'", text)
    return m.group(1) if m else None


class EngineLint(unittest.TestCase):
    def test_no_source_repo_names_in_shipped_files(self):
        pattern = review_hits_pattern()
        self.assertTrue(pattern, "sync-from-source.sh 에서 REVIEW_HITS 패턴을 찾지 못함")
        found = hits(pattern)
        self.assertEqual(found, [], "소스 저장소 전용 이름이 배포 파일에 남아 있음:\n" + "\n".join(found))

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
        gate_a = (ROOT / "skills" / "gate-a" / "SKILL.md").read_text(encoding="utf-8")
        examples = [b for b in re.findall(r"```markdown\n(.*?)```", gate_a, re.S) if "### 레인 판정" in b]
        self.assertEqual(len(examples), 1, "gate-a 에 `### 레인 판정` 예시 블록이 정확히 하나 있어야 함")
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


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    unittest.main(verbosity=2)
