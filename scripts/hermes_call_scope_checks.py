"""Offline probes through native Hermes call sites, not a simulated plugin API.

Imported by smoke_hermes_context_engine after installing in an isolated profile.
Only the provider/HTTP endpoints and unrelated formatting/observer work are mocked.
"""

from __future__ import annotations

import copy
import json
from types import SimpleNamespace
from unittest.mock import patch


def exercise_call_scope(manager, agent, request, engine) -> dict:
    import httpx
    from agent import auxiliary_client, relay_runtime
    from agent.turn_api_request import build_api_request
    from hermes_cli.middleware import apply_llm_request_middleware
    from openai import OpenAI
    from plugins.memory.mem0._backend import PlatformBackend, SelfHostedBackend

    from rtk_hermes_plus.engine_bridge import current

    context = {
        "session_id": agent.session_id,
        "turn_id": "scope-turn",
        "api_request_id": "scope-attempt",
        "api_call_count": 1,
        "api_mode": agent.api_mode,
        "model": agent.model,
        "provider": agent.provider,
    }
    baseline, pending = copy.deepcopy(request), current()
    agent._reset_stream_delivery_tracking = lambda: None
    agent._reapply_reasoning_echo_for_provider = lambda messages: None
    agent._build_api_kwargs = lambda messages, **kwargs: {
        **copy.deepcopy(request),
        "messages": messages,
    }
    agent._empty_content_retries = 0
    agent._is_user_initiated_turn = False
    agent.max_tokens = 1024
    with (
        patch("hermes_cli.plugins._delivery_manager", return_value=manager),
        patch("agent.turn_api_request.sanitize_outbound_kwargs"),
        patch("agent.turn_api_request.strip_images_for_rejecting_model"),
        patch("agent.turn_api_request._fire_pre_api_request_hook"),
        patch(
            "agent.conversation_loop._redecorate_prompt_cache_for_provider",
            side_effect=lambda _agent, messages, **kwargs: (
                messages,
                None,
                agent.tools,
            ),
        ),
    ):
        results = []
        for retry in (0, 1):
            built = build_api_request(
                agent,
                api_messages=copy.deepcopy(request["messages"]),
                _moa_prepared_request=None,
                tools_for_api=agent.tools,
                system_message=request["messages"][0],
                messages=request["messages"],
                original_user_message=request["messages"][-1]["content"],
                approx_tokens=20000,
                total_chars=len(json.dumps(request)),
                retry_count=retry,
                api_call_count=1,
                api_request_id=f"main-retry-{retry}",
                api_start_time=0.0,
                effective_task_id="scope-task",
                turn_id="scope-turn",
            )
            assert built._llm_middleware_trace and built.api_kwargs != request
            results.append(built.api_kwargs)
        assert results[0] == results[1] and request == baseline
        # Read the REAL auxiliary task ContextVar, which is inherited by protected
        # provider worker threads; even forged main metadata cannot override it.
        with auxiliary_client._relay_aux_call_scope(("classifier",), {}):
            attempted = apply_llm_request_middleware(request, **context)
            assert not attempted.changed and attempted.payload == request
            engine.select_context([{"role": "user", "content": "helper only"}])
            assert current() is pending
        delegated = SimpleNamespace(lease=SimpleNamespace(parent_session_id="parent"))
        token = relay_runtime._CURRENT_TURN.set(delegated)
        try:
            attempted = apply_llm_request_middleware(request, **context)
            assert not attempted.changed and attempted.payload == request
        finally:
            relay_runtime._CURRENT_TURN.reset(token)
        # Already-safe paths must not begin calling the TT request hook. Keep it
        # registered, and assert it is not invoked while native clients run.
        seen = []

        def provider(kwargs):
            seen.append(copy.deepcopy(kwargs))
            return {"choices": [{"message": {"role": "assistant", "content": "ok"}}]}

        wire_inputs = []

        def http_provider(req):
            wire_inputs.append((req.url.path, json.loads(req.content)))
            if req.url.path.endswith("/embeddings"):
                return httpx.Response(
                    200,
                    json={
                        "object": "list",
                        "data": [
                            {"object": "embedding", "index": 0, "embedding": [0.5]}
                        ],
                        "model": "fixture-embedder",
                        "usage": {"prompt_tokens": 1, "total_tokens": 1},
                    },
                )
            return httpx.Response(200, json={"results": []})

        with patch.object(
            manager,
            "invoke_middleware",
            side_effect=AssertionError("native internal call reached TT"),
        ):
            # Native auxiliary call dispatch still uses separate observer hooks.
            auxiliary = {
                "model": "gpt-4o",
                "messages": [
                    {"role": "user", "content": 'Classify exactly: "a  b"; 12.300\n'}
                ],
            }
            for task in ("title", "classifier", "compression", "vision", "approval"):
                with auxiliary_client._relay_aux_call_scope((task,), {}):
                    auxiliary_client._relay_sync_completion(
                        SimpleNamespace(base_url="https://fixture.invalid/v1"),
                        copy.deepcopy(auxiliary),
                        create=provider,
                    )
            assert seen == [auxiliary] * 5
            texts = ['Do NOT compact: "a  b"\n9007199254740993', "second exact text"]
            with OpenAI(
                api_key="fixture",
                base_url="https://fixture.invalid/v1",
                http_client=httpx.Client(transport=httpx.MockTransport(http_provider)),
            ) as sdk:
                sdk.embeddings.create(model="fixture-embedder", input=texts)
            assert wire_inputs[-1][1]["input"] == texts
            # Exercise the actual Hermes Mem0 cloud and HTTP adapters. No Mem0
            # dependency/account is created; cloud client and HTTP transport are fakes.
            query = 'Exact ranking query: "spaced  words" and 12.300\n'
            ranking = []
            backend = PlatformBackend.__new__(PlatformBackend)
            backend._client = SimpleNamespace(
                search=lambda *args, **kwargs: (
                    ranking.append((args, kwargs)),
                    {"results": []},
                )[1]
            )
            assert (
                backend.search(query, filters={"user_id": "fixture"}, rerank=True) == []
            )
            assert ranking == [
                (
                    (query,),
                    {"filters": {"user_id": "fixture"}, "top_k": 10, "rerank": True},
                )
            ]
            http_backend = SelfHostedBackend(
                "fixture",
                "https://fixture.invalid",
                transport=httpx.MockTransport(http_provider),
            )
            try:
                http_backend.search(query, filters={"user_id": "fixture"})
                assert wire_inputs[-1][1]["query"] == query
                http_backend.add(
                    auxiliary["messages"], user_id="fixture", agent_id="fixture"
                )
                assert wire_inputs[-1][1]["messages"] == auxiliary["messages"]
            finally:
                http_backend.close()
        assert current() is pending and request == baseline
    return {
        "real_main_request_builder": True,
        "provider_retry_unchanged": True,
        "real_auxiliary_context_veto": True,
        "real_delegated_role_veto": True,
        "native_auxiliary_clients_bypass": True,
        "sdk_embedding_input_exact": True,
        "native_mem0_rerank_query_exact": True,
        "native_mem0_http_inputs_exact": True,
        "main_engine_binding_preserved": True,
        "paid_calls": 0,
    }
