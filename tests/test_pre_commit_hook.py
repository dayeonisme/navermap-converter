from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "scripts" / "pre-commit"


def _init_repo(tmp_path: Path, filename: str, content: str) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
    target = repo / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", filename], cwd=repo, check=True, capture_output=True, text=True)
    return repo


def _run_hook(tmp_path: Path, content: str, filename: str = "probe.txt") -> subprocess.CompletedProcess[str]:
    repo = _init_repo(tmp_path, filename, content)
    return subprocess.run([str(HOOK)], cwd=repo, capture_output=True, text=True)


def _sensitive_samples() -> list[str]:
    local_user = "local" + ".user"
    sheet_id = "1LXUJ4So6ZV" + "BFwse5pr0BzQgKgtLbv8Gv2pMLk82Oo5Y"
    watcha_user = "ZBm5" + "RJM945d46"
    return [
        f"cd /Users/{local_user}/dev/project\n",
        "project=" + "apply" + "home-watch\n",
        "TELEGRAM_CHAT_ID=" + "580" + "6848967\n",
        f"SPREADSHEET_ID='{sheet_id}'\n",
        "DHLOTTERY_ID=" + "ppp" + "lotto11\n",
        f"url=https://pedia.watcha.com/ko-KR/users/{watcha_user}/contents/movies\n",
    ]


@pytest.mark.parametrize("content", _sensitive_samples())
def test_pre_commit_blocks_privacy_patterns(tmp_path: Path, content: str) -> None:
    assert HOOK.exists()

    result = _run_hook(tmp_path, content)

    assert result.returncode == 1
    assert "Commit blocked" in result.stdout


def test_pre_commit_blocks_env_files(tmp_path: Path) -> None:
    assert HOOK.exists()

    result = _run_hook(tmp_path, "TOKEN=placeholder\n", ".env")

    assert result.returncode == 1
    assert "BLOCKED FILE" in result.stdout


def test_pre_commit_blocks_locally_configured_privacy_pattern(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path, "probe.txt", "owner=local-sensitive-identity\n")
    subprocess.run(
        ["git", "config", "--local", "--add", "cinelog.privacyPattern", "local-sensitive-identity"],
        cwd=repo, check=True, capture_output=True, text=True,
    )
    result = subprocess.run([str(HOOK)], cwd=repo, capture_output=True, text=True)
    assert result.returncode == 1
    assert "local privacy pattern" in result.stdout
