#!/usr/bin/env python3
"""
보고 수치를 모델이 세지 않고 명령이 만든다 — 「사실 블록」 생성기.

왜: 2026-10-15 실사용에서 최종 보고의 개수가 실측과 어긋났다(「5개 반영」 → 실제 훅 4 + 시험 4,
「새 시험은 모두 수정 전 실패」 → 19건 중 17건). 사용자가 매번 「대조 검증」을 요청해 사람이
교차 검증을 대신하고 있었다. 공식 Claude Code best practices 는 「성공을 주장하지 말고 증거를
보여라」고 한다. 이 스크립트가 만든 블록을 그대로 붙이고, 보고의 수치는 이 블록에 있는 것만 쓴다.

출력(Markdown, `--json` 이면 JSON):
  1. 변경 파일 — 범주(code·tests·skills·docs)별 개수와 목록. git 기준(`--base` 이후 + 작업 트리
     + 추적 안 된 새 파일)
  2. 시험 합계 — `--junit` 으로 준 JUnit XML 들의 tests·failures·errors·skipped
  3. 기준 커밋 재현표(선택) — `--fail-on-base "<명령>" --base-junit <상대경로>`: 기준 커밋의 임시
     worktree 에 지금의 시험 파일만 얹어 명령을 돌리고, 시험별 결과(fails_on_base / passes_on_base /
     errors_on_base)를 센다. 「새 시험 N건 중 M건이 수정 전 실패」 문장의 출처가 된다

표준 라이브러리만 쓴다. 실패한 부분은 블록에 「확인 불가」로 적고 숫자를 지어내지 않는다.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_TEST_RE = re.compile(
    r"(^|/)(tests?|__tests__)/|(^|/)src/test/|(^|/)test_[^/]+$|_test\.[^/]+$|\.(test|spec)\.[^/]+$"
)


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=True).stdout


def category(path):
    if _TEST_RE.search(path):
        return "tests"
    if path.startswith("skills/"):
        return "skills"
    if path.endswith(".md"):
        return "docs"
    return "code"


def changed_files(repo, base=None, both_sides=False):
    """[(상태, 경로)] — base 이후 커밋 + 작업 트리 변경 + 추적 안 된 새 파일.

    이름 바꾸기는 새 경로만 남긴다. `both_sides=True` 면 옛 경로도 「D」로 넣는다 —
    레인 범위 훅이 보호 경로 밖으로 옮긴 파일을 놓치지 않게(S7, 2026-10-22).
    """
    ref = base or "HEAD"
    out = git(repo, "diff", "--name-status", "-M", ref)
    files = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            status = parts[0][0]
            files.append((status, parts[-1]))
            if both_sides and status == "R" and len(parts) >= 3:
                files.append(("D", parts[1]))
    for path in git(repo, "ls-files", "--others", "--exclude-standard").splitlines():
        if path.strip():
            files.append(("A", path.strip()))
    return sorted(set(files), key=lambda x: x[1])


def changed_lines(repo, base=None):
    """{경로: 추가+삭제 줄 수} — `changed_files` 와 같은 범위(추적 안 된 새 파일은 전체 줄 수).

    이진 파일은 0줄로 센다(파일 수에는 `changed_files` 쪽에서 잡힌다).
    """
    lines = {}
    # -z: 이름 바꾸기가 `옛 => 새` 한 칸이 아니라 「빈 경로 칸 + 옛 + 새」 토큰으로 온다
    tokens = git(repo, "diff", "--numstat", "-M", "-z", base or "HEAD").split("\0")
    i = 0
    while i < len(tokens):
        parts = tokens[i].split("\t")
        i += 1
        if len(parts) < 3:
            continue
        added, deleted = (int(n) if n.isdigit() else 0 for n in parts[:2])
        path = parts[2]
        if not path:          # 이름 바꾸기 — 다음 두 토큰이 옛 경로·새 경로
            path = tokens[i + 1] if i + 1 < len(tokens) else ""
            i += 2
        if path:
            lines[path] = added + deleted
    for path in git(repo, "ls-files", "--others", "--exclude-standard").splitlines():
        path = path.strip()
        if path:
            try:
                with open(os.path.join(repo, path), "rb") as f:
                    lines[path] = f.read().count(b"\n")
            except OSError:
                lines[path] = 0
    return lines


def junit_cases(path):
    """JUnit XML → [(시험 ID, 결과)] 결과 = passed·failed·error·skipped."""
    root = ET.parse(path).getroot()
    cases = []
    for tc in root.iter("testcase"):
        tid = "::".join(x for x in (tc.get("classname"), tc.get("name")) if x)
        if tc.find("failure") is not None:
            result = "failed"
        elif tc.find("error") is not None:
            result = "error"
        elif tc.find("skipped") is not None:
            result = "skipped"
        else:
            result = "passed"
        cases.append((tid, result))
    return cases


def junit_totals(paths):
    totals = {"tests": 0, "passed": 0, "failed": 0, "error": 0, "skipped": 0}
    for p in paths:
        for _, result in junit_cases(p):
            totals["tests"] += 1
            totals[result] += 1
    return totals


def fail_on_base(repo, base, command, base_junit, test_paths):
    """기준 커밋 worktree 에 지금의 시험 파일을 얹어 명령을 돌린 시험별 결과."""
    tmp = tempfile.mkdtemp(prefix="report-facts-")
    wt = os.path.join(tmp, "base")
    try:
        git(repo, "worktree", "add", "--detach", "-q", wt, base)
        for rel in test_paths:
            src = os.path.join(repo, rel)
            if os.path.isfile(src):
                dst = os.path.join(wt, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
        run = subprocess.run(command, shell=True, cwd=wt, capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
        junit = os.path.join(wt, base_junit)
        if not os.path.isfile(junit):
            return {"error": f"JUnit 결과 없음: {base_junit} (명령 종료 코드 {run.returncode})"}
        mapping = {"failed": "fails_on_base", "error": "errors_on_base",
                   "passed": "passes_on_base", "skipped": "skipped_on_base"}
        return {"cases": [(tid, mapping[r]) for tid, r in junit_cases(junit)],
                "exit_code": run.returncode}
    finally:
        subprocess.run(["git", "-C", repo, "worktree", "remove", "--force", wt],
                       capture_output=True)
        shutil.rmtree(tmp, ignore_errors=True)


def build(args):
    repo = os.path.abspath(args.repo)
    facts = {"repo": repo, "base": args.base or "HEAD (커밋 안 된 변경)"}
    try:
        files = changed_files(repo, args.base)
        by_cat = {}
        for status, path in files:
            by_cat.setdefault(category(path), []).append(f"{status} {path}")
        facts["changed"] = {"total": len(files),
                            "by_category": {k: len(v) for k, v in sorted(by_cat.items())},
                            "files": by_cat}
    except Exception as e:  # git 실패는 숫자 대신 사유로
        facts["changed"] = {"error": str(e)}
    if args.junit:
        try:
            facts["tests"] = junit_totals(args.junit)
        except Exception as e:
            facts["tests"] = {"error": str(e)}
    if args.fail_on_base:
        if not (args.base and args.base_junit):
            facts["fail_on_base"] = {"error": "--fail-on-base 에는 --base 와 --base-junit 이 필요"}
        else:
            tests = [p.split(" ", 1)[1] for p in facts.get("changed", {}).get("files", {}).get("tests", [])
                     if not p.startswith("D ")]
            try:
                facts["fail_on_base"] = fail_on_base(repo, args.base, args.fail_on_base,
                                                     args.base_junit, tests)
            except Exception as e:
                facts["fail_on_base"] = {"error": str(e)}
    return facts


def to_markdown(f):
    lines = [f"### 사실 블록 (report_facts) — 기준 `{f['base']}`", ""]
    ch = f.get("changed", {})
    if "error" in ch:
        lines.append(f"- 변경 파일: 확인 불가 — {ch['error']}")
    else:
        cats = " · ".join(f"{k} {v}" for k, v in ch["by_category"].items()) or "없음"
        lines.append(f"- 변경 파일 **{ch['total']}개** ({cats})")
        for cat, items in sorted(ch["files"].items()):
            lines.append(f"  - {cat}: " + ", ".join(f"`{i}`" for i in items))
    t = f.get("tests")
    if t is not None:
        if "error" in t:
            lines.append(f"- 시험 합계: 확인 불가 — {t['error']}")
        else:
            lines.append(f"- 시험 **{t['passed']}/{t['tests']} 통과** "
                         f"(실패 {t['failed']} · 오류 {t['error']} · 건너뜀 {t['skipped']})")
    fb = f.get("fail_on_base")
    if fb is not None:
        if "error" in fb:
            lines.append(f"- 기준 커밋 재현: 확인 불가 — {fb['error']}")
        else:
            counts = {}
            for _, r in fb["cases"]:
                counts[r] = counts.get(r, 0) + 1
            n = len(fb["cases"])
            lines.append(f"- 기준 커밋 재현: 시험 **{n}건 중 {counts.get('fails_on_base', 0)}건이 수정 전 실패**"
                         f" · 수정 전 통과 {counts.get('passes_on_base', 0)}건(회귀 방지용)"
                         f" · 수정 전 오류 {counts.get('errors_on_base', 0)}건")
            for tid, r in fb["cases"]:
                if r != "fails_on_base":
                    lines.append(f"  - {r}: `{tid}`")
    lines += ["", "> 보고·WORKLOG·CHANGELOG 의 개수는 이 블록에서만 옮긴다. 「모두·전부」 대신 N/M 으로 쓴다."]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="보고용 사실 블록 생성")
    ap.add_argument("--repo", default=".", help="git 저장소(기본: 현재 폴더)")
    ap.add_argument("--base", help="비교 기준 커밋·브랜치(없으면 HEAD — 커밋 안 된 변경만)")
    ap.add_argument("--junit", action="append", default=[], help="JUnit XML(여러 번 가능)")
    ap.add_argument("--fail-on-base", help="기준 커밋 worktree 에서 돌릴 시험 명령")
    ap.add_argument("--base-junit", help="그 명령이 worktree 안에 남기는 JUnit XML 상대경로")
    ap.add_argument("--json", action="store_true", help="JSON 으로 출력")
    args = ap.parse_args(argv)
    facts = build(args)
    print(json.dumps(facts, ensure_ascii=False, indent=2) if args.json else to_markdown(facts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
