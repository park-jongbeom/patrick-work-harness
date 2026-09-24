#!/usr/bin/env python3
"""skill_usage_aggregator.py 시험 (HARNESS-ANALYTICS-PORT-1, 2026-09-24).

이 집계기는 원본 작업공간에만 있고 **배포본에는 없었다**. 그래서
`skill-usage-auto` 훅이 `hooks.json` 에 등록돼 매 응답마다 돌면서
**아무 일도 하지 않고 exit 0** 이었다(실측). 이식하면서 시험을 같이 붙인다.

합성 JSONL 로 재는 이유: 실제 transcript 를 읽으면 실행 환경마다 결과가
달라져 시험이 결정론적이지 않다.
"""

import importlib.util
import json
import os
import shutil
import tempfile
import unittest
import unittest.mock
from datetime import datetime, timedelta, timezone
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "sua", os.path.join(os.path.dirname(__file__), "skill_usage_aggregator.py")
)
sua = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(sua)


def skill_entry(skill, ts, session="S1", tool_id=None):
    """Skill tool_use 형태의 transcript 한 줄."""
    return {
        "timestamp": ts.isoformat().replace("+00:00", "Z"),
        "sessionId": session,
        "message": {
            "content": [{
                "type": "tool_use",
                "name": "Skill",
                "id": tool_id or f"tu_{skill}_{ts.timestamp()}",
                "input": {"skill": skill},
            }]
        },
    }


class AggregatorTestBase(unittest.TestCase):

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="agg_"))
        self.proj = self.root / "proj-one"
        self.proj.mkdir()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, entries, name="s1.jsonl"):
        with open(self.proj / name, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")


class TestAggregate(AggregatorTestBase):

    def test_counts_skill_invocations(self):
        now = datetime.now(timezone.utc)
        self.write([
            skill_entry("gate-a", now, tool_id="t1"),
            skill_entry("gate-a", now, tool_id="t2"),
            skill_entry("gate-b", now, tool_id="t3"),
        ])
        r = sua.aggregate(self.root, now - timedelta(days=30))
        self.assertIsInstance(r, dict)

    def test_empty_projects_dir_does_not_crash(self):
        """새 환경의 첫 실행 — transcript 가 하나도 없어도 돌아야 한다."""
        now = datetime.now(timezone.utc)
        r = sua.aggregate(self.root, now - timedelta(days=30))
        self.assertIsInstance(r, dict)

    def test_malformed_line_is_skipped(self):
        """깨진 줄 하나가 전체 집계를 죽이지 않는다."""
        now = datetime.now(timezone.utc)
        with open(self.proj / "s1.jsonl", "w", encoding="utf-8") as f:
            f.write("{not json at all\n")
            f.write(json.dumps(skill_entry("gate-a", now)) + "\n")
        r = sua.aggregate(self.root, now - timedelta(days=30))
        self.assertIsInstance(r, dict)


class TestDashboardOutput(AggregatorTestBase):

    def test_writes_markdown_with_all_nine_skills(self):
        now = datetime.now(timezone.utc)
        self.write([skill_entry("gate-a", now)])
        # main() 은 sys.argv 를 읽으므로 format_dashboard 를 직접 검증한다.
        # 실측 계약: window_start·window_end 둘 다 datetime 이다(일수 아님).
        start = now - timedelta(days=30)
        r = sua.aggregate(self.root, start)
        md = sua.format_dashboard(r, now.strftime("%Y-%m"), start, now)
        for s in sua.NINE_SKILLS:
            self.assertIn(s, md, f"{s} 가 표에 없다")

    def test_creates_missing_output_directory(self):
        """🔴 출력 경로의 **부모가 없어도** 써야 한다 (2026-09-25 실측 결함).

        종전 `write_text` 는 부모가 없으면 `FileNotFoundError` 로 죽었고,
        호출자인 `skill-usage-auto` 훅은 예외를 stderr 로만 남기고 **exit 0**
        이라 새 프로젝트에서 집계가 **매번 실패하면서 아무도 모르는** 상태가
        됐다. 실제로 이 PC 의 볼트에는 9월분이 끝내 안 생겼다.

        기존 시험이 놓친 이유: 전부 `tempfile.mkdtemp()` 로 **이미 있는**
        디렉터리에 썼다. 여기서는 **없는 경로**를 일부러 준다.
        """
        now = datetime.now(timezone.utc)
        self.write([skill_entry("gate-a", now)])
        out = self.root / "없는폴더" / "또없는폴더" / "skill_usage_2026-09.md"
        self.assertFalse(out.parent.exists(), "전제: 부모가 없어야 한다")

        argv = ["skill_usage_aggregator.py",
                "--projects-dir", str(self.root), "--output", str(out)]
        with unittest.mock.patch.object(sua.sys, "argv", argv):
            rc = sua.main()

        self.assertEqual(rc, 0)
        self.assertTrue(out.is_file(), "부모 디렉터리를 만들고 썼어야 한다")
        self.assertIn("gate-a", out.read_text(encoding="utf-8"))

    def test_deployed_skill_list_matches_shipped_skills(self):
        """집계 대상 9종이 실제 배포 스킬과 일치한다.

        2026-09-24 이식 시 원본 목록(`error-log`·`export-roles`)이 이 배포본에
        없는 스킬을 세고 있었다. 목록이 어긋나면 **없는 스킬을 0회로 보고**
        「통합·폐기 후보」라고 말하게 된다.
        """
        skills_dir = Path(__file__).resolve().parent.parent / "skills"
        shipped = {p.name for p in skills_dir.iterdir()
                   if p.is_dir() and not p.name.startswith(".")}
        self.assertEqual(set(sua.NINE_SKILLS), shipped,
                         f"집계 목록과 배포 스킬이 다르다: "
                         f"집계만={set(sua.NINE_SKILLS) - shipped} "
                         f"배포만={shipped - set(sua.NINE_SKILLS)}")


class TestWindowTimezone(unittest.TestCase):
    """🔴 윈도우 끝(=생성일·월 라벨)은 **현지 시간대**로 잡아야 한다.

    2026-09-25 01:34(KST) 에 돌린 산출물에 「생성일 2026-09-24」 가 찍혔다.
    `datetime.now(timezone.utc)` 로 잡아서, KST 기준 **자정~오전 9시 사이에
    날짜가 하루 밀린** 것이다. 월말 자정 직후면 **월 라벨까지 전달로 밀려**
    엉뚱한 파일에 덮어쓴다.

    어제 「시간대를 일반화했다」고 적었지만 실제로는 시간대 분포 집계에만
    적용됐고 윈도우 계산은 UTC 그대로였다 — 일반화가 절반만 됐던 자리다.
    """

    def test_month_label_uses_local_timezone(self):
        """KST 01:00 = UTC 전날 16:00. 월 라벨이 UTC 기준이면 하루 밀린다."""
        root = Path(tempfile.mkdtemp(prefix="tz_"))
        (root / "p").mkdir()
        out = root / "out.md"
        try:
            argv = ["skill_usage_aggregator.py",
                    "--projects-dir", str(root), "--output", str(out)]
            with unittest.mock.patch.object(sua.sys, "argv", argv):
                sua.main()
            text = out.read_text(encoding="utf-8")
            expected = datetime.now(sua.KST).strftime("%Y-%m-%d")
            self.assertIn(f"**생성일**: {expected}", text,
                          "생성일이 현지 날짜와 다르다 — UTC 로 잡고 있지 않은지 볼 것")
        finally:
            shutil.rmtree(root, ignore_errors=True)


class TestPortability(unittest.TestCase):
    """이식 시 일반화한 부분 — 사설 경로·시간대."""

    def test_default_projects_dir_is_under_home(self):
        """사설 절대경로가 박혀 있으면 다른 PC 에서 0건을 돌려준다."""
        self.assertIn(str(Path.home()), str(sua.DEFAULT_PROJECTS_DIR))
        self.assertNotIn("/home/ubuntu", str(sua.DEFAULT_PROJECTS_DIR))

    def test_timezone_offset_is_configurable(self):
        """기본 KST(+9), 환경변수로 조정 가능."""
        self.assertEqual(sua.KST.utcoffset(None), timedelta(hours=9))


if __name__ == "__main__":
    unittest.main(verbosity=2)
