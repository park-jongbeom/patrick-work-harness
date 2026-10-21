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

ENGINE_LINT_ROOT 로 다른 트리(예: `git archive` 로 푼 과거 커밋)를 검사할 수 있다.
"""
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


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    unittest.main(verbosity=2)
