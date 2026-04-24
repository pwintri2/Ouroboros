# Docker Output - Exact Test Results from Gordon

## Command Executed (As Requested by Codex)

```bash
cd /home/pwintri2/Negesydd
docker run --rm \
  -v /home/pwintri2/Negesydd:/negesydd \
  -v negesydd-dev:/negesydd/.venv \
  negesydd:dev-sandbox \
  python -m pytest tests/test_config_parser.py -v
```

## Output

```
============================= test session starts ==============================
platform linux -- Python 3.11.15, pytest-9.0.3, pluggy-1.6.0 -- /usr/local/bin/python
cachedir: .pytest_cache
rootdir: /negesydd
plugins: timeout-2.4.0, cov-7.1.0, asyncio-1.3.0, anyio-4.13.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_fixture_loop_scope=function
collecting ... collected 6 items

tests/test_config_parser.py::test_parse_yaml_plan_file PASSED            [ 16%]
tests/test_config_parser.py::test_parse_json_plan PASSED                 [ 33%]
tests/test_config_parser.py::test_extended_prompt_parsing PASSED         [ 50%]
tests/test_config_parser.py::test_plain_prompt_fallback PASSED           [ 66%]
tests/test_config_parser.py::test_invalid_dependency_raises_config_error PASSED [ 83%]
tests/test_config_parser.py::test_load_config_alias PASSED               [100%]

============================== 6 passed in 0.05s ==============================
```

---

## Second Command Executed (Full Test Suite)

```bash
cd /home/pwintri2/Negesydd
docker run --rm \
  -v /home/pwintri2/Negesydd:/negesydd \
  -v negesydd-dev:/negesydd/.venv \
  negesydd:dev-sandbox \
  python -m pytest tests/ -v
```

## Output

```
============================= test session starts ==============================
platform linux -- Python 3.11.15, pytest-9.0.3, pluggy-1.6.0 -- /usr/local/bin/python
cachedir: .pytest_cache
rootdir: /negesydd
plugins: timeout-2.4.0, cov-7.1.0, asyncio-1.3.0, anyio-4.13.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_fixture_loop_scope=function
collecting ... collected 24 items

tests/test_agent_pool.py::test_agent_pool_init PASSED                    [  4%]
tests/test_agent_pool.py::test_discover_agents PASSED                    [  8%]
tests/test_agent_pool.py::test_add_agent PASSED                          [ 12%]
tests/test_agent_pool.py::test_agent_health_check PASSED                 [ 16%]
tests/test_agent_pool.py::test_unhealthy_stale_agent PASSED              [ 20%]
tests/test_config_parser.py::test_parse_yaml_plan_file PASSED            [ 25%]
tests/test_config_parser.py::test_parse_json_plan PASSED                 [ 29%]
tests/test_config_parser.py::test_extended_prompt_parsing PASSED         [ 33%]
tests/test_config_parser.py::test_plain_prompt_fallback PASSED           [ 37%]
tests/test_config_parser.py::test_invalid_dependency_raises_config_error PASSED [ 41%]
tests/test_config_parser.py::test_load_config_alias PASSED               [ 45%]
tests/test_logger.py::test_logger_init PASSED                            [ 50%]
tests/test_logger.py::test_logger_info PASSED                            [ 54%]
tests/test_logger.py::test_correlation_id PASSED                         [ 58%]
tests/test_logger.py::test_error_with_exception PASSED                   [ 62%]
tests/test_message_queue.py::test_queue_put_get PASSED                   [ 66%]
tests/test_message_queue.py::test_queue_empty PASSED                     [ 70%]
tests/test_message_queue.py::test_dead_letter_queue PASSED               [ 75%]
tests/test_message_queue.py::test_callback_registration PASSED           [ 79%]
tests/test_message_queue.py::test_priority_ordering PASSED               [ 83%]
tests/test_message_types.py::test_message_creation PASSED                [ 87%]
tests/test_message_types.py::test_message_json_serialization PASSED      [ 91%]
tests/test_message_types.py::test_error_message PASSED                   [ 95%]
tests/test_message_types.py::test_correlation_id_from_context PASSED     [100%]

============================== 24 passed in 0.08s ==============================
```

---

## Summary

**Module 5 Test:** ✅ 6/6 PASSED (0.05s)
**Full Suite Test:** ✅ 24/24 PASSED (0.08s)

No failures, no errors, no warnings.

**Decision:** All tests passing. No patches needed. Ready for Module 6.
