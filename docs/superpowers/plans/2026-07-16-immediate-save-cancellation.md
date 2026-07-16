# Immediate Save Cancellation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `저장 취소` interrupt the active async save task immediately and close the progress stream cleanly.

**Architecture:** Retain the current cancellation flag as a defensive between-item check, but also store the active `asyncio.Task` and cancel it from `/cancel`. Convert `CancelledError` into one `cancelled` progress event, clear all job state in `finally`, and terminate SSE on both terminal event types.

**Tech Stack:** Python 3.9, FastAPI 0.111, asyncio, pytest 8.3, unittest.mock

## Global Constraints

- Cancellation must interrupt login waiting, list creation, and individual address saving.
- Preserve `/cancel` success response `{"status": "cancelling"}` and no-job 404 behavior.
- Emit exactly one `{"type": "cancelled"}` terminal event for task cancellation.
- Clear `_job_active` and `_job_task` for success, failure, and cancellation.
- Keep the existing `_job_cancelled` callback check as defense in depth.
- Do not shut down the FastAPI server or reusable browser context.

---

## File Map

- Modify `main.py`: own the background task, cancel it, translate cancellation to progress, and close SSE.
- Modify `tests/test_api.py`: verify task ownership, immediate cancellation, state cleanup, and SSE termination.

### Task 1: Own and cancel the background save task

**Files:**
- Modify: `main.py:39-42,124-143,175-197,225-296`
- Modify: `tests/test_api.py`

**Interfaces:**
- Consumes: `/save`, `/retry`, `/cancel`, and `_run_save(address_dicts, list_name_override)`.
- Produces: `_job_task: asyncio.Task | None`; `/cancel` calls `cancel()` on the live task.

- [ ] **Step 1: Add a failing endpoint cancellation test**

Add `asyncio`, `MagicMock`, and `patch` imports to `tests/test_api.py`, then append:

```python
@pytest.mark.asyncio
async def test_cancel_job_실행중_task_cancel_호출():
    import main

    task = MagicMock()
    task.done.return_value = False
    main._job_active = True
    main._job_cancelled = False
    main._job_task = task
    try:
        result = await main.cancel_job()

        assert result == {"status": "cancelling"}
        assert main._job_cancelled is True
        task.cancel.assert_called_once_with()
    finally:
        main._job_active = False
        main._job_cancelled = False
        main._job_task = None
```

- [ ] **Step 2: Add a failing task-reference test for `/save`**

Append:

```python
@pytest.mark.asyncio
async def test_save_addresses_생성한_task_참조_보관():
    import main

    started = asyncio.Event()
    release = asyncio.Event()

    async def blocked_save(*_args):
        started.set()
        await release.wait()

    main._job_active = False
    main._job_task = None
    with patch("main._run_save", side_effect=blocked_save):
        result = await main.save_addresses(main.SaveRequest(addresses=[]))
        await started.wait()
        task = main._job_task

        assert result == {"status": "accepted"}
        assert isinstance(task, asyncio.Task)

        release.set()
        await task

    main._job_active = False
    main._job_task = None
```

- [ ] **Step 3: Run the two tests and verify RED**

Run:

```bash
python3 -m pytest \
  tests/test_api.py::test_cancel_job_실행중_task_cancel_호출 \
  tests/test_api.py::test_save_addresses_생성한_task_참조_보관 -v
```

Expected: failures because `main._job_task` does not exist and `/cancel` never calls `Task.cancel()`.

- [ ] **Step 4: Store and cancel the active task**

Add beside the other singleton state:

```python
_job_task: asyncio.Task | None = None
```

In `save_addresses()` and `retry_addresses()`, include `_job_task` in `global` and replace the bare `create_task` call with:

```python
    _job_task = asyncio.create_task(_run_save(...))
```

Keep the existing argument lists at each call site.

Update `cancel_job()` to:

```python
@app.post("/cancel")
async def cancel_job():
    global _job_cancelled
    if not _job_active:
        raise HTTPException(status_code=404, detail="진행 중인 작업이 없습니다")
    _job_cancelled = True
    if _job_task is not None and not _job_task.done():
        _job_task.cancel()
    return {"status": "cancelling"}
```

- [ ] **Step 5: Run the focused tests and verify GREEN**

Run the Step 3 command again.

Expected: both tests pass.

### Task 2: Convert task cancellation to terminal progress and cleanup

**Files:**
- Modify: `main.py:211-222,225-296`
- Modify: `tests/test_api.py`

**Interfaces:**
- Consumes: an `asyncio.CancelledError` raised at any await inside `_run_save()`.
- Produces: one `cancelled` queue event, `_job_active == False`, `_job_task is None`, and a completed SSE generator.

- [ ] **Step 1: Add a failing cancellation-cleanup test**

Append:

```python
@pytest.mark.asyncio
async def test_run_save_대기중_cancelled_event와_상태정리():
    import main

    entered = asyncio.Event()

    async def wait_forever():
        entered.set()
        await asyncio.Event().wait()

    browser = MagicMock()
    browser.is_logged_in = AsyncMock(side_effect=wait_forever)
    main._progress_queue = asyncio.Queue()
    main._job_active = True

    with patch("main.get_browser", return_value=browser):
        task = asyncio.create_task(main._run_save([], None))
        main._job_task = task
        await entered.wait()
        task.cancel()
        await task

    assert main._job_active is False
    assert main._job_task is None
    assert await main._progress_queue.get() == {"type": "cancelled"}
```

- [ ] **Step 2: Add a failing SSE terminal-event test**

Append:

```python
@pytest.mark.asyncio
async def test_stream_progress_cancelled에서_종료():
    import main

    main._progress_queue = asyncio.Queue()
    await main._progress_queue.put({"type": "cancelled"})
    stream = main._stream_progress()

    assert "cancelled" in await stream.__anext__()
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(stream.__anext__(), timeout=0.1)
```

- [ ] **Step 3: Run the two tests and verify RED**

Run:

```bash
python3 -m pytest \
  tests/test_api.py::test_run_save_대기중_cancelled_event와_상태정리 \
  tests/test_api.py::test_stream_progress_cancelled에서_종료 -v
```

Expected: `_run_save` propagates `CancelledError`; the stream waits beyond `cancelled` and times out.

- [ ] **Step 4: Handle cancellation and clear task state**

In `_run_save()`, add `_job_task` to the global declaration and add immediately before its `finally`:

```python
    except asyncio.CancelledError:
        if _progress_queue is not None:
            await _progress_queue.put({"type": "cancelled"})
```

Change the `finally` block to:

```python
    finally:
        _job_active = False
        _job_task = None
```

Change `_stream_progress()`'s terminal check to:

```python
        if event.get("type") in {"done", "cancelled"}:
            break
```

- [ ] **Step 5: Run API tests and verify GREEN**

Run:

```bash
python3 -m pytest tests/test_api.py -v
```

Expected: all API tests pass.

- [ ] **Step 6: Commit immediate cancellation**

```bash
git add main.py tests/test_api.py
git commit -m "fix: 저장 작업 즉시 취소"
```

### Task 3: Full and live cancellation verification

**Files:**
- Verify only; no planned source changes.

**Interfaces:**
- Consumes: the completed cancel API and running local server.
- Produces: fresh evidence that cancellation releases the job without creating a Naver list.

- [ ] **Step 1: Run all tests**

Run:

```bash
python3 -m pytest -q
```

Expected: all tests pass with zero failures.

- [ ] **Step 2: Restart the server**

Stop the current port-8000 process and run:

```bash
/usr/bin/python3 main.py
```

Expected: Uvicorn listens on `http://127.0.0.1:8000`.

- [ ] **Step 3: Start and cancel a no-write verification job**

Run `/save` with an empty address list and a non-empty `list_name`, then immediately call `/cancel`:

```bash
curl -sS http://127.0.0.1:8000/save -H 'Content-Type: application/json' \
  --data-binary '{"addresses":[],"list_name":"cancel-verification"}'
curl -sS -X POST http://127.0.0.1:8000/cancel
```

The non-empty list name disables list creation, and the empty addresses disable place writes. Expected: save returns `accepted`; cancel returns `cancelling`.

- [ ] **Step 4: Verify the job is released**

After cancellation, call `/cancel` again and `/parse-text`:

```bash
curl -sS -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:8000/cancel
curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/parse-text \
  -H 'Content-Type: application/json' --data-binary '{"text":"서울 종로구 필운동 202"}'
```

Expected: second cancel returns 404 and parse-text returns 200, proving `_job_active` was cleared.

- [ ] **Step 5: Inspect final changes**

Run:

```bash
git diff HEAD~1 --check
git status --short
```

Expected: no whitespace errors; only the user's existing untracked screenshot files remain.
