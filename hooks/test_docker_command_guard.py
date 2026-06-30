#!/usr/bin/env python3
"""docker-command-guard.py 단위 테스트.

차단 훅 — 틀린 docker 명령은 exit 2, 정본·비-docker·비-Bash 는 exit 0.
프로토콜: stdin JSON { tool_name, tool_input: {command} }.

설정 주입: CLAUDE_PROJECT_DIR 환경변수로 임시 harness-answers.yml 경로를 제공.
"""

import json
import os
import subprocess
import sys
import tempfile

SCRIPT = os.path.join(os.path.dirname(__file__), "docker-command-guard.py")


def run_hook(command=None, tool_name="Bash", payload=None, answers_yml=None):
    """훅을 서브프로세스로 실행, (returncode, stderr) 반환.

    answers_yml: harness-answers.yml 내용 문자열 (None → 파일 없음 = fail-open).
    """
    if payload is None:
        payload = {"tool_name": tool_name}
        if command is not None:
            payload["tool_input"] = {"command": command}

    env = os.environ.copy()

    if answers_yml is not None:
        tmp = tempfile.mkdtemp()
        claude_dir = os.path.join(tmp, ".claude")
        os.makedirs(claude_dir, exist_ok=True)
        with open(os.path.join(claude_dir, "harness-answers.yml"), "w") as f:
            f.write(answers_yml)
        env["CLAUDE_PROJECT_DIR"] = tmp
    else:
        # 설정 없음 — 기존 환경 CLAUDE_PROJECT_DIR 격리
        env.pop("CLAUDE_PROJECT_DIR", None)

    proc = subprocess.run(
        [sys.executable, SCRIPT],
        input=json.dumps(payload),
        capture_output=True, text=True,
        env=env,
    )
    return proc.returncode, proc.stderr.strip()


# ── 고정 차단: TTY 플래그 (설정 무관, 모든 프로젝트 공통) ──

def test_block_tty_it():
    rc, err = run_hook("docker exec -it my-container sh")
    assert rc == 2 and "DOCKER-GUARD" in err


def test_block_tty_ti():
    rc, _ = run_hook("docker exec -ti my-container bash")
    assert rc == 2


def test_block_tty_separate_i_t():
    rc, _ = run_hook("docker exec -i -t my-container sh")
    assert rc == 2


# ── 설정 기반 차단: docker_blocked_containers ──

_ANSWERS_BLOCKED = """\
docker_blocked_containers:
  - name: "absent-api"
    reason: "컨테이너 부재"
  - name: "runtime-only"
    gradle: true
    reason: "런타임 전용, Gradle 없음"
"""


def test_block_absent_container():
    rc, err = run_hook("docker exec absent-api ./gradlew test", answers_yml=_ANSWERS_BLOCKED)
    assert rc == 2 and "부재" in err


def test_block_absent_container_with_flags():
    rc, _ = run_hook("docker exec -e FOO=bar absent-api ls", answers_yml=_ANSWERS_BLOCKED)
    assert rc == 2


def test_block_gradle_on_runtime_container():
    rc, err = run_hook("docker exec runtime-only ./gradlew test", answers_yml=_ANSWERS_BLOCKED)
    assert rc == 2 and "런타임" in err


def test_pass_runtime_container_non_gradle():
    # gradle 아닌 명령은 허용
    rc, _ = run_hook("docker exec runtime-only cat /app/application.yml", answers_yml=_ANSWERS_BLOCKED)
    assert rc == 0


# ── fail-open: harness-answers.yml 없으면 컨테이너 규칙 없음 ──

def test_pass_no_answers_file_arbitrary_container():
    # 설정 없으면 TTY 외에는 차단 없음
    rc, _ = run_hook("docker exec any-container ./gradlew test", answers_yml=None)
    assert rc == 0


def test_pass_empty_blocked_list():
    rc, _ = run_hook(
        "docker exec any-container ls",
        answers_yml="docker_blocked_containers: []\n",
    )
    assert rc == 0


# ── 통과 케이스 ──

def test_pass_canonical_no_tty():
    rc, _ = run_hook("docker exec my-frontend npm test -- --run")
    assert rc == 0


def test_pass_compose_run():
    rc, _ = run_hook(
        'docker compose -f /path/to/docker-compose-test.yml run --rm test-runner'
    )
    assert rc == 0


def test_pass_non_docker():
    rc, _ = run_hook("ls -la /tmp")
    assert rc == 0


def test_pass_empty_command():
    rc, _ = run_hook(command=None)
    assert rc == 0


def test_pass_non_bash_tool():
    rc, _ = run_hook(payload={"tool_name": "Edit", "tool_input": {"file_path": "x.md"}})
    assert rc == 0


def test_pass_malformed_payload():
    proc = subprocess.run(
        [sys.executable, SCRIPT], input="not json",
        capture_output=True, text=True,
    )
    assert proc.returncode == 0


if __name__ == "__main__":
    import importlib
    mod = sys.modules[__name__]
    fns = [getattr(mod, n) for n in dir(mod) if n.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
