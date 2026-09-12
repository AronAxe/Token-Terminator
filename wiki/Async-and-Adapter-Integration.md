# Async and Adapter Integration

Hermes is turnkey, but the core can be connected to another agent runtime.

## Minimum adapter contract

Your host needs:

- stable `session_id`, request ID, and tool-call ID values;
- a tool-result transformation boundary;
- a final provider-request middleware boundary;
- a model-visible recovery tool backed by `Runtime.tool`.

The host must treat `None` or an adapter exception as pass-through.

## Synchronous example

```python
from pathlib import Path
from rtk_hermes_plus.config import Config
from rtk_hermes_plus.plugin import Runtime

runtime = Runtime(
    Config(
        mode="balanced",
        db_path=Path(".token-terminator/artifacts.sqlite3"),
        ledger_enabled=False,
    ),
    profile_name="my-agent",
)

reduced = runtime.transform_tool_result(
    tool_name=name,
    args=arguments,
    result=result,
    session_id=session_id,
    tool_call_id=call_id,
)
provider_result = reduced if reduced is not None else result
```

Call `runtime.llm_request_middleware(...)` immediately before provider dispatch and use its returned request only when the decision is non-`None`.

## AsyncRuntime

```python
from rtk_hermes_plus import AsyncRuntime, CancellationToken

async_runtime = AsyncRuntime(runtime)
cancel = CancellationToken()

reduced = await async_runtime.transform_tool_result(
    tool_name="search_files",
    args={"pattern": "ContextEngine"},
    result=large_result,
    session_id=session_id,
    tool_call_id=call_id,
    cancellation=cancel,
)
```

Compiler, SQLite, and telemetry work can run in an executor. Active RTK subprocesses use cancellation-aware async paths. If a caller cancels while an atomic SQLite operation is already running in a worker, that worker may finish; its result is discarded at the adapter boundary.

Token Terminator does not intercept provider response streams.

## Canonical tool mapping

For the built-in native compressor, adapters should map equivalent host tools to canonical names such as:

- `search_files`
- `process`
- optionally `read_file` in aggressive mode
- `terminal` for terminal rewriting/temporal logic

Do not silently change the semantics of the host tool while mapping names.
