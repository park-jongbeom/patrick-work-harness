#!/usr/bin/env python3
"""Gate A 과거 교훈 조회 — error_topics 에서 다음 작업과 맞는 교훈을 최대 2건 꺼낸다.

gate-a/SKILL.md 가 `` !`python3 ${CLAUDE_SKILL_DIR}/lessons_lookup.py "${CLAUDE_PROJECT_DIR}"` ``
로 부른다. 스킬이 렌더링될 때 Claude Code 가 먼저 실행하고, 그 출력이 스킬 본문에
들어간다 — 모델이 조회를 「잊는」 경로가 없다 (HARNESS-LESSON-1, 2026-10-21).

왜 결정적 조회인가: 실사용 기록에서 Gate A 4회 중 error_topics 를 읽은 것은 0회였고,
같은 실패 계열이 날짜를 바꿔 다시 기록됐다. 모델 재량에 맡긴 조회는 일어나지 않는다
(Vercel 평가 56% 미호출, AWM 18.5%). 넣는 양은 2건으로 묶는다 — 꺼낸 기억이 많을수록
성능이 떨어졌다(ReasoningBank 1건 49.7% → 4건 44.4%).

계약:
  * 어떤 경우에도 exit 0 — 이 명령이 실패하면 gate-a 호출 전체가 중단된다.
  * 출력은 사실 기록이다(명령조 금지). 무엇을 할지는 gate-a 본문이 정한다.
  * 읽기만 한다.

교훈 위치 (error-topics-guard.py 와 같은 규칙):
  .claude/harness-answers.yml → error_topics_path (프로젝트 기준 상대) 가 있으면 그곳,
  없으면 code_repos 각각의 <프로젝트 상위>/<repo>/docs/rules/error_topics,
  그리고 <프로젝트>/docs/rules/error_topics 가 있으면 함께 본다.

질의: --query "키워드" 가 있으면 그것, 없으면 SESSION_INDEX.md 의 next_action
  (직전 Gate E 가 다음 세션 작업으로 적은 줄)과 CURRENT_SESSION.md 의 세션 주제·작업 의도.
"""
import argparse
import glob
import math
import os
import re
import sys

MAX_SHOWN = 2
MIN_SCORE = 3.0      # IDF 가중 점수 하한
MIN_DISTINCT = 2     # 서로 다른 일치 단어 수 하한 (적용 조건에서 맞으면 1개로 충분)
AUTO_QUERY_FACTOR = 2.0  # next_action 같은 긴 문장 질의는 우연한 겹침이 많아 하한을 높인다
FIELD_CHARS = 220


def read(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def answers(project):
    text = read(os.path.join(project, ".claude", "harness-answers.yml"))
    out = {"code_repos": [], "error_topics_path": None}
    if not text:
        return out
    m = re.search(r"^error_topics_path\s*:\s*[\"']?([^\"'#\n]+?)[\"']?\s*(?:#.*)?$", text, re.M)
    if m:
        out["error_topics_path"] = m.group(1).strip()
    in_repos = False
    for line in text.splitlines():
        if re.match(r"^code_repos\s*:", line):
            in_repos = True
            inline = re.search(r"\[(.*)\]", line)
            if inline:
                out["code_repos"] += [x.strip().strip("\"'") for x in inline.group(1).split(",") if x.strip()]
                in_repos = False
            continue
        if in_repos:
            if re.match(r"^\S", line):
                break
            m = re.match(r"^\s+-\s+[\"']?(.+?)[\"']?\s*(?:#.*)?$", line)
            if m:
                out["code_repos"].append(m.group(1).strip())
    return out


def topic_dirs(project):
    a = answers(project)
    dirs = []
    if a["error_topics_path"]:
        dirs.append(os.path.join(project, a["error_topics_path"]))
    else:
        parent = os.path.dirname(os.path.abspath(project))
        dirs += [os.path.join(parent, r, "docs", "rules", "error_topics") for r in a["code_repos"]]
    dirs.append(os.path.join(project, "docs", "rules", "error_topics"))
    seen, out = set(), []
    for d in dirs:
        real = os.path.realpath(d)
        if real not in seen and os.path.isdir(d):
            seen.add(real)
            out.append(d)
    return out


# 항목 제목: 새 형식은 `## [날짜] …`, 옛 저장소는 `## 분류` 아래 `### [날짜] …` 로 적었다.
HEADING = re.compile(r"^(#{2,4})\s+\[(\d{4}-\d{2}-\d{2})\]\s*(.*)$")
ANY_HEADING = re.compile(r"^(#{1,6})\s")


def field(body, name):
    m = re.search(r"\*\*%s\*\*\s*[:：]\s*(.*)$" % re.escape(name), body, re.M)
    return m.group(1).strip() if m else ""


def entries(dirs):
    out = []
    for d in dirs:
        for path in sorted(glob.glob(os.path.join(d, "*.md"))):
            if os.path.basename(path).lower() == "readme.md":
                continue
            lines = read(path).splitlines()
            for i, line in enumerate(lines):
                m = HEADING.match(line)
                if not m:
                    continue
                level, date, title = len(m.group(1)), m.group(2), m.group(3)
                end = len(lines)
                for j in range(i + 1, len(lines)):  # 같은 수준 이상의 다음 제목에서 끊는다
                    h = ANY_HEADING.match(lines[j])
                    if h and len(h.group(1)) <= level:
                        end = j
                        break
                body = "\n".join(lines[i + 1:end])
                out.append({
                    "date": date, "title": title.strip(), "file": os.path.basename(path),
                    "dir": d, "when": field(body, "적용 조건"), "rule": field(body, "재발 방지 규칙"),
                    "evidence": field(body, "근거"), "status": field(body, "상태"),
                    "recur": len(re.findall(r"\*\*재발\*\*", body)),
                })
    return out


WORD = re.compile(r"[A-Za-z][A-Za-z0-9_.\-]{2,}|[가-힣]{2,}|\d{3,}")
# 일반어와 이 분야에서 거의 모든 교훈에 나오는 말은 일치로 치지 않는다.
STOP = {"the", "and", "for", "with", "from", "this", "that", "not", "gate", "session",
        "세션", "작업", "수정", "확인", "다음", "진행", "결과", "추가", "변경", "있는", "없는", "하는",
        "경우", "때문", "문제", "관련", "대한", "검증", "코드", "적용", "파일", "실행", "사용", "이후",
        "이전", "필요", "반드시", "먼저", "직접", "모든", "같은", "다른", "규칙", "오류", "실패", "시험"}
FIELD_WEIGHT = {"when": 2.0, "title": 1.0, "rule": 0.5}


def tokens(text):
    out = set()
    for w in WORD.findall(text or ""):
        w = w.lower().strip(".-")
        if not w or w in STOP:
            continue
        if re.match(r"[가-힣]", w):
            # 조사가 붙어도 맞도록 단어 앞 두 글자 하나만 쓴다. 모든 2글자 조각을 쓰면
            # 「으로·하고」 같은 어미끼리 맞았고, 앞머리를 둘 쓰면 한 단어가 두 번 셌다.
            out.add(w[:2])
        else:
            out.add(w)
    return out - STOP


def idf_table(items):
    """드문 단어일수록 무겁게 — 1 + ln((N+1)/(df+1))."""
    df = {}
    for e in items:
        for tok in e["_tokens"]:
            df[tok] = df.get(tok, 0) + 1
    n = len(items)
    return lambda tok: 1.0 + math.log((n + 1) / (df.get(tok, 0) + 1))


def score(entry, query_tokens, idf):
    """(점수, 서로 다른 일치 단어 수, 적용 조건 일치 여부)."""
    s, matched, in_when = 0.0, set(), False
    for name, weight in FIELD_WEIGHT.items():
        common = entry["_fields"][name] & query_tokens
        if name == "when" and common:
            in_when = True
        for tok in common:
            if tok not in matched:  # 같은 단어를 여러 칸에서 거듭 세지 않는다
                s += weight * idf(tok)
                matched.add(tok)
    return s, len(matched), in_when


def query_text(project, explicit):
    if explicit:
        return explicit, "--query"
    parts = []
    idx = read(os.path.join(project, "SESSION_INDEX.md"))
    m = re.search(r"^\s*next_action\s*:\s*(.+)$", idx, re.M)
    if m:
        parts.append(re.split(r"이전:|직전:", m.group(1))[0])
    cur = read(os.path.join(project, "CURRENT_SESSION.md"))
    for label in ("세션 주제", "작업 의도"):
        m = re.search(r"\*\*%s\*\*\s*[:：]\s*(.+)$" % label, cur, re.M)
        if m:
            parts.append(m.group(1))
    return " ".join(parts), "next_action·세션 주제"


def dedupe(items):
    """같은 날 같은 제목으로 형제 저장소에 복사된 항목은 하나로 합친다 (2건 한도를 중복이 차지하지 않게)."""
    merged = {}
    for e in items:
        key = (e["date"], re.sub(r"\s+", " ", e["title"]).strip())
        if key in merged:
            merged[key]["copies"] += 1
            merged[key]["recur"] = max(merged[key]["recur"], e["recur"])
        else:
            e["copies"] = 1
            merged[key] = e
    return list(merged.values())


def clip(s):
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= FIELD_CHARS else s[:FIELD_CHARS - 1] + "…"


def run(project, explicit_query):
    dirs = topic_dirs(project)
    print("### 과거 교훈 조회 결과 (lessons_lookup.py 가 생성 — 사실 기록)")
    if not dirs:
        print("- 교훈 저장소 없음: harness-answers.yml 에 error_topics_path 또는 code_repos 가 없고, "
              "docs/rules/error_topics 도 없다.")
        return
    all_entries = dedupe(entries(dirs))
    live = [e for e in all_entries if "대체됨" not in e["status"]]
    q, source = query_text(project, explicit_query)
    qt = tokens(q)
    for e in live:
        e["_fields"] = {k: tokens(e[k]) for k in FIELD_WEIGHT}
        e["_tokens"] = set().union(*e["_fields"].values())
    idf = idf_table(live)
    floor = MIN_SCORE if explicit_query else MIN_SCORE * AUTO_QUERY_FACTOR
    scored = []
    for e in live:
        s, distinct, in_when = score(e, qt, idf)
        if s >= floor and (distinct >= MIN_DISTINCT or in_when):
            scored.append((round(s, 1), e))
    # 점수 → 재발 기록 수 → 최근 날짜 순
    hits = sorted(scored, key=lambda x: (x[0], x[1]["recur"], x[1]["date"]), reverse=True)[:MAX_SHOWN]
    print(f"- 조회 범위: 저장소 {len(dirs)}곳 · 항목 {len(live)}건 (대체됨 {len(all_entries) - len(live)}건 제외)")
    print(f"- 질의({source}): {clip(q) or '(비어 있음)'}")
    if not hits:
        print(f"- 일치하는 교훈: 없음 (점수 하한 {floor:g} 미달)")
        return
    for s, e in hits:
        where = e["file"] if e["copies"] == 1 else f"{e['file']} 외, 저장소 {e['copies']}곳"
        print(f"- [{e['date']}] {clip(e['title'])}  ({where}, 일치 점수 {s}, 재발 기록 {e['recur']}회)")
        print(f"  - 적용 조건: {clip(e['when']) or '(옛 형식 — 칸 없음)'}")
        print(f"  - 재발 방지 규칙: {clip(e['rule']) or '(칸 없음)'}")
        print(f"  - 근거: {clip(e['evidence']) or '(칸 없음)'}")


def main(argv=None):
    try:
        ap = argparse.ArgumentParser(add_help=False)
        ap.add_argument("project", nargs="?", default=None)
        ap.add_argument("--query", default=None)
        args, _ = ap.parse_known_args(argv)
        project = args.project or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
        if not os.path.isdir(project):
            project = os.getcwd()
        run(project, args.query)
    except Exception as exc:  # 조회 실패가 Gate A 를 막아선 안 된다
        print(f"- 교훈 조회 실패({type(exc).__name__}) — 조회 없이 진행한다.")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
    sys.exit(0)
