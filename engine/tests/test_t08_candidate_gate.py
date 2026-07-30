from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_GATE = REPOSITORY_ROOT / "scripts" / "t08_candidate_gate.sh"
CANDIDATE_TREE_CHECK = REPOSITORY_ROOT / "scripts" / "t08_candidate_tree_check.sh"


def _run_git(repository: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )


def _candidate_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "candidate"
    scripts = repository / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(CANDIDATE_GATE, scripts / CANDIDATE_GATE.name)
    shutil.copy2(CANDIDATE_TREE_CHECK, scripts / CANDIDATE_TREE_CHECK.name)
    (repository / "tracked.txt").write_text("committed\n", encoding="utf-8")

    _run_git(repository, "init", "-b", "main")
    _run_git(repository, "config", "user.name", "T08 Gate Test")
    _run_git(repository, "config", "user.email", "t08-gate@local.invalid")
    _run_git(repository, "config", "commit.gpgsign", "false")
    _run_git(repository, "add", ".")
    _run_git(repository, "commit", "-m", "candidate")
    return repository


def _run_candidate_check(repository: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(repository / "scripts" / CANDIDATE_TREE_CHECK.name)],
        cwd=repository,
        env={
            **os.environ,
            "T08_CANDIDATE_BASE_REF": "main",
        },
        check=False,
        capture_output=True,
        text=True,
    )


def _run_candidate_gate(
    repository: Path,
    tmp_path: Path,
) -> subprocess.CompletedProcess[str]:
    artifact_root = tmp_path / "candidate-artifacts"
    artifact_root.mkdir()
    command_root = tmp_path / "candidate-commands"
    command_root.mkdir()
    for command in ("curl", "jq", "npm", "supabase", "uv", "zip"):
        executable = command_root / command
        executable.write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
        executable.chmod(0o755)
    return subprocess.run(
        [str(repository / "scripts" / CANDIDATE_GATE.name)],
        cwd=repository,
        env={
            **os.environ,
            "PATH": f"{command_root}{os.pathsep}{os.environ['PATH']}",
            "T08_CANDIDATE_BASE_REF": "main",
            "T08_CHECK_ONLY": "true",
            "TMPDIR": str(artifact_root),
        },
        check=False,
        capture_output=True,
        text=True,
    )


def test_candidate_tree_check_accepts_a_clean_checkout(tmp_path: Path) -> None:
    repository = _candidate_repository(tmp_path)

    result = _run_candidate_check(repository)

    assert result.returncode == 0, result.stderr
    assert "Candidate tree check passed" in result.stdout


def test_candidate_gate_cannot_bypass_a_dirty_preflight(tmp_path: Path) -> None:
    repository = _candidate_repository(tmp_path)
    (repository / "tracked.txt").write_text("changed\n", encoding="utf-8")

    result = _run_candidate_gate(repository, tmp_path)

    assert result.returncode != 0
    assert "candidate worktree must be clean" in result.stderr
    assert "Provisioning a blank migrated Supabase database" not in result.stdout


def test_candidate_gate_ignores_legacy_check_only_after_clean_preflight(
    tmp_path: Path,
) -> None:
    repository = _candidate_repository(tmp_path)

    result = _run_candidate_gate(repository, tmp_path)

    assert result.returncode != 0
    assert "Candidate tree check passed" in result.stdout
    assert "Provisioning a blank migrated Supabase database" in result.stdout
    assert "Candidate gate passed" not in result.stdout


@pytest.mark.parametrize(
    "dirty_kind",
    ["unstaged", "staged", "untracked", "assume-unchanged", "skip-worktree"],
)
def test_candidate_tree_check_rejects_dirty_checkout(
    tmp_path: Path,
    dirty_kind: str,
) -> None:
    repository = _candidate_repository(tmp_path)
    if dirty_kind == "untracked":
        (repository / "untracked.txt").write_text("untracked\n", encoding="utf-8")
    else:
        if dirty_kind in {"assume-unchanged", "skip-worktree"}:
            _run_git(repository, "update-index", f"--{dirty_kind}", "tracked.txt")
        (repository / "tracked.txt").write_text("changed\n", encoding="utf-8")
        if dirty_kind == "staged":
            _run_git(repository, "add", "tracked.txt")

    result = _run_candidate_check(repository)

    assert result.returncode != 0
    assert "candidate worktree must be clean" in result.stderr
