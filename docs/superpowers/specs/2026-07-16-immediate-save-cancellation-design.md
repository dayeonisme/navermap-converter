# 저장 작업 즉시 취소 설계

## 목표

사용자가 `저장 취소`를 누르면 로그인 대기, 리스트 생성, 개별 주소 저장 중 어느 단계에 있더라도 저장 작업을 즉시 중단하고 UI를 정상 대기 상태로 되돌린다.

## 원인

- 현재 `/cancel`은 `_job_cancelled = True`만 설정한다.
- 이 플래그는 `save_addresses_to_naver()`의 주소 항목 사이에서만 확인한다.
- 로그인 대기 최대 120초, 리스트 생성, 단일 주소 저장 중에는 플래그를 확인하지 않는다.
- `cancelled` 이벤트를 보내더라도 SSE 서버 스트림은 `done`에서만 종료되므로 연결이 남을 수 있다.

## 작업 수명주기

- 전역 `_job_task: asyncio.Task | None`에 현재 `/save` 또는 `/retry` 백그라운드 작업을 저장한다.
- 새 작업 생성 전에 기존 `_job_active` 검사를 유지한다.
- `/cancel`은 `_job_cancelled = True`를 설정하고, 실행 중인 `_job_task`가 있으면 `cancel()`을 호출한다.
- `_run_save()`는 `asyncio.CancelledError`를 잡아 진행 큐에 `{"type": "cancelled"}`를 한 번 넣은 뒤 종료한다.
- `_run_save()`의 `finally`에서 `_job_active = False`와 `_job_task = None`을 모두 수행한다.
- 기존 단계 사이의 `_job_cancelled` 확인은 방어 계층으로 유지한다.

## SSE 및 UI

- `_stream_progress()`는 `done`뿐 아니라 `cancelled` 이벤트에서도 루프를 종료한다.
- 기존 브라우저 UI는 `cancelled` 이벤트에서 저장/취소 버튼과 EventSource를 이미 정리하므로 변경하지 않는다.
- `/cancel` 응답은 기존 `{"status": "cancelling"}`을 유지한다.
- 진행 중인 작업이 없으면 기존 404 동작을 유지한다.

## 오류 처리

- 사용자가 요청한 `CancelledError`는 일반 저장 오류로 표시하지 않는다.
- 취소 도중 열린 주소 탭은 기존 `finally: await tab.close()` 경로에서 닫힌다.
- 서버 자체와 재사용 가능한 기본 브라우저 컨텍스트는 유지한다.

## 검증

- `/save`가 생성한 실제 비동기 작업 참조를 보관하는지 테스트한다.
- `/cancel`이 작업의 `cancel()`을 호출하는지 테스트한다.
- 로그인 대기처럼 완료되지 않는 await 중에도 취소 후 `_job_active`가 해제되고 `cancelled` 이벤트가 생성되는지 테스트한다.
- SSE 스트림이 `cancelled` 이벤트 직후 종료되는지 테스트한다.
- 기존 항목 사이 취소 테스트와 전체 테스트를 함께 실행한다.
- 실행 중인 서버에서 통제된 대기 작업을 시작한 뒤 취소 API가 작업 상태를 해제하는지 검증한다. 이 검증에서는 네이버 계정에 리스트를 생성하지 않는다.
