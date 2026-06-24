#!/usr/bin/env python3
"""docker-command-guard.py 단위 테스트.

차단 훅 — 틀린 docker 명령은 exit 2, 정본·비-docker·비-Bash 는 exit 0.
프로토콜: stdin JSON { tool_name, tool_input: {command} }.
"""

import json
import os
import subprocess
import sys

SCRIPT = os.path.join(os.path.dirname(__file__), "docker-command-guard.py")


def run_hook(command=None, tool_name="Bash", payload=None):
    """훅을 서브프로세스로 실행, (returncode, stderr) 반환."""
    if payload is None:
        payload = {"tool_name": tool_name}
        if command is not None:
            payload["tool_input"] = {"command": command}
    proc = subprocess.run(
        [sys.executable, SCRIPT],
        input=json.dumps(payload),
        capture_output=True, text=True,
    )
    return proc.returncode, proc.stderr.strip()


# ── 차단 케이스 (exit 2) ──

def test_block_tty_it():
    rc, err = run_hook("docker exec -it react-web-ga sh")
    assert rc == 2 and "DOCKER-GUARD" in err


def test_block_tty_ti():
    rc, _ = run_hook("docker exec -ti college-crawler-local bash")
    assert rc == 2


def test_block_tty_separate_i_t():
    rc, _ = run_hook("docker exec -i -t react-web-ga sh")
    assert rc == 2


def test_block_wrong_ga_api_container():
    rc, err = run_hook("docker exec ga-api-platform ./gradlew test")
    assert rc == 2 and "부재" in err


def test_block_wrong_ga_api_with_flags():
    rc, _ = run_hook("docker exec -e FOO=bar ga-api-platform ls")
    assert rc == 2


def test_block_matching_api_gradlew():
    rc, err = run_hook("docker exec ga-matching-api ./gradlew test")
    assert rc == 2 and "JRE" in err


# ── 통과 케이스 (exit 0) ──

def test_pass_canonical_react():
    rc, _ = run_hook("docker exec react-web-ga npm test -- --run")
    assert rc == 0


def test_pass_canonical_crawler():
    rc, _ = run_hook("docker exec college-crawler-local pytest tests/")
    assert rc == 0


def test_pass_canonical_ga_test_compose():
    rc, _ = run_hook(
        'sg docker -c "docker compose -f '
        '/media/ubuntu/data120g/ga-api-platform/docker-compose-test.yml '
        'run --rm ga-test"'
    )
    assert rc == 0


def test_pass_matching_api_runtime_ops():
    # ga-matching-api 런타임 명령(gradle 아님)은 정당 → 통과
    rc, _ = run_hook("docker exec ga-matching-api cat /app/application.yml")
    assert rc == 0


def test_pass_non_docker():
    rc, _ = run_hook("ls -la /media/ubuntu/data120g")
    assert rc == 0


def test_pass_empty_command():
    rc, _ = run_hook(command=None)
    assert rc == 0


def test_pass_non_bash_tool():
    rc, _ = run_hook(payload={"tool_name": "Edit",
                              "tool_input": {"file_path": "x.md"}})
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
