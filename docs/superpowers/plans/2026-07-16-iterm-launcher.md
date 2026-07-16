# iTerm2 런처 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `NaverMap.app`이 iTerm2에서 서버를 열고, iTerm2가 없으면 Terminal로 안전하게 대체 실행되도록 한다.

**Architecture:** `launcher/NaverMap.applescript`에 iTerm2 실행과 TTY 기반 세션 정리 분기를 추가한다. `launcher/build.sh`는 기존 경로 치환과 번들 빌드를 유지하며, 컴파일된 스크립트에 필요한 분기가 남는지 테스트가 검증한다.

**Tech Stack:** AppleScript, Bash, Python unittest, macOS `osacompile`.

## Global Constraints

- macOS 전용 `NaverMap.app`의 더블클릭 토글 UX를 유지한다.
- iTerm2가 설치되면 iTerm2를 우선 사용하고, 없거나 자동화가 실패하면 Terminal을 사용한다.
- 서버 PID 종료는 세션 창 닫기 실패와 무관하게 수행한다.
- iTerm2 프로파일과 기존 네이버 저장 기능은 변경하지 않는다.

---

### Task 1: 런처 소스 계약 테스트 추가

**Files:**
- Create: `tests/test_launcher.py`
- Modify: `launcher/NaverMap.applescript`

**Interfaces:**
- Consumes: `launcher/NaverMap.applescript`의 텍스트 AppleScript 소스
- Produces: iTerm2 우선·Terminal 대체·TTY 세션 정리 요구사항을 검사하는 `unittest.TestCase`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path
import unittest


SCRIPT = Path(__file__).parents[1] / "launcher" / "NaverMap.applescript"


class LauncherSourceTests(unittest.TestCase):
    def test_prefers_iterm2_with_terminal_fallback(self):
        source = SCRIPT.read_text()
        self.assertIn('application id "com.googlecode.iterm2"', source)
        self.assertIn('tell application "Terminal"', source)
        self.assertIn('create window with default profile', source)

    def test_closes_matching_iterm_session_by_tty(self):
        source = SCRIPT.read_text()
        self.assertIn('sessions of w', source)
        self.assertIn('(tty of s) is theTTY', source)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_launcher -v`

Expected: FAIL because the source does not yet reference iTerm2.

- [ ] **Step 3: Write minimal implementation**

Add an AppleScript `application id "com.googlecode.iterm2"` availability check. Start a default-profile window and send the existing Python command to its current session. On failure use the existing Terminal block. In the stop branch, locate and close an iTerm2 session whose `tty` equals the server TTY, then retain Terminal cleanup as a fallback.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_launcher -v`

Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add launcher/NaverMap.applescript tests/test_launcher.py
git commit -m "feat: iTerm2에서 런처 실행"
```

### Task 2: 컴파일과 앱 빌드 검증

**Files:**
- Modify: `launcher/NaverMap.applescript`
- Modify: `NaverMap.app` (generated bundle)
- Test: `tests/test_launcher.py`

**Interfaces:**
- Consumes: Task 1의 AppleScript source contract
- Produces: macOS AppleScript 컴파일 가능한 launcher와 재생성된 `NaverMap.app`

- [ ] **Step 1: Add the failing compiler test**

```python
import subprocess
import tempfile

    def test_source_compiles(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "NaverMap.app"
            result = subprocess.run(
                ["osacompile", "-o", str(output), str(SCRIPT)],
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_launcher.LauncherSourceTests.test_source_compiles -v`

Expected: FAIL only if the changed AppleScript syntax is invalid.

- [ ] **Step 3: Correct the AppleScript syntax if needed**

Use iTerm2’s `create window with default profile`, `write text`, and `tty` session properties. Keep `__APP_DIR__` unresolved in source because shell path substitution occurs in `launcher/build.sh`.

- [ ] **Step 4: Run focused and full tests**

Run: `python3 -m unittest tests.test_launcher -v && pytest -q`

Expected: launcher tests PASS and the existing test suite PASS.

- [ ] **Step 5: Rebuild the app**

Run: `bash launcher/build.sh`

Expected: output contains `✓ 빌드 완료` and `NaverMap.app` exists.

- [ ] **Step 6: Commit**

```bash
git add launcher/NaverMap.applescript tests/test_launcher.py
git commit -m "test: iTerm2 런처 컴파일 검증"
```
