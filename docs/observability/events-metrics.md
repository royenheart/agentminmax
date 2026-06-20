# AgentMinMax Events And Metrics

Generated from Doxygen XML plus the live metric definitions in `agentminmax.metrics`.
Doxygen XML is generated from `agentminmax/metrics.py`, `agentminmax/models.py`, and `agentminmax/ingest.py`; this Markdown is rendered from those code comments plus live metric definition data.

## Pipeline

- `agentminmax.ingest.normalize_events()` converts native Codex logs and benchmark result records into normalized events.
- `agentminmax.ingest.build_observation()` aggregates normalized events into `AgentSession` and `BenchmarkRun` models.
- `agentminmax.metrics.enrich_session_metrics()` emits atomic events and grouped session metrics.
- `agentminmax.metrics.enrich_benchmark_metrics()` emits grouped benchmark metrics from aggregated benchmark runs.
- The dashboard renders the same event and metric objects; detail actions show each metric's inputs and formula.

## Atomic Events

| Event | Category | Unit | Source | Meaning | Formula | Labels |
| --- | --- | --- | --- | --- | --- | --- |
| `model.size_billions` | model | B | session.model.parameters.declared_size, session.model.parameters.size, or agentminmax/data/model_sizes.json | Model scale normalized to billions of parameters. | `parse(model.parameters.declared_size \|\| model.parameters.size) \|\| fallback(model.name)` | `raw_size`, `source`, `canonical_model`, `confidence`, `architecture` |
| `model.active_size_billions` | model | B | agentminmax/data/model_sizes.json | Activated parameter count for mixture-of-experts models when known. | `fallback(model.name).active_parameter_billions` | `raw_size`, `source`, `canonical_model`, `confidence`, `architecture` |
| `model.absorption` | model | ratio | model.size_billions | Coarse estimate of the task complexity absorbed by model scale. | `piecewise(model.size_billions)` | `source`, `canonical_model` |
| `complexity.intrinsic_score` | complexity | score | tokens, tools, benchmark results, code metrics, and duration_seconds | Task complexity before model absorption. | `log1p(tokens.total)/2 + tool/benchmark/code/time pressure terms` | none |
| `complexity.effective_score` | complexity | score | complexity.intrinsic_score and model.absorption | Complexity remaining after model-size absorption. | `complexity.intrinsic_score * (1 - model.absorption)` | none |
| `complexity.chaos_score` | complexity | score | benchmark failures, code.lines_deleted, and benchmark quality gap | Proxy for unstable iteration and regression pressure. | `failed_benchmarks + 0.01*code.lines_deleted + 0.25*quality_gap` | none |
| `token.input` | llm | tokens | token_usage/token_usage_total events | Input tokens consumed by the session. | `direct observation` | none |
| `token.output` | llm | tokens | token_usage/token_usage_total events | Output tokens produced by the session. | `direct observation` | none |
| `token.cached_input` | llm | tokens | token_usage/token_usage_total events | Input tokens served from model/provider cache when reported. | `direct observation` | none |
| `code.files_changed` | engineering | files | code_metric or Codex patch_apply_end events | Changed file count. | `direct observation` | none |
| `code.lines_added` | engineering | lines | code_metric or Codex patch_apply_end events | Added line count. | `direct observation` | none |
| `code.lines_deleted` | engineering | lines | code_metric or Codex patch_apply_end events | Deleted line count. | `direct observation` | none |
| `code.lines_changed` | engineering | lines | code.lines_added and code.lines_deleted | Total edit volume. | `code.lines_added + code.lines_deleted` | none |
| `benchmark.task_result` | benchmark | tasks | benchmark_result events and runs session_benchmark_map | Task-level benchmark results associated with a session. | `count(session.benchmarks)` | none |
| `tool.call` | agent_behavior | calls | tool_call events and Codex response_item tool calls | Tool invocation count by tool name. | `count(tool_call where labels.tool=tool)` | `tool` |
| `tool.error` | agent_behavior | calls | trace tool events and tool outputs | Tool calls whose trace status or output indicates an error. | `count(trace.tool where status=error or output contains failure markers)` | none |
| `plan.update` | planning | updates | update_plan tool and trace events | Plan update count. | `max(tool.update_plan, count(trace.update_plan))` | none |
| `chaos.tool_entropy` | chaos | bits | tool.call distribution | Shannon entropy of tool usage. | `-sum(p(tool) * log2(p(tool)))` | none |
| `output.code_density` | local_optimum | lines/call | code.lines_changed and tool.call | Changed lines divided by total tool calls. | `code.lines_changed / tool_call_count` | none |

## Session Metric Groups

### Model

- Group id: `model`
- Dashboard display: `cards`

| Metric | Unit | Meaning | Formula | Inputs |
| --- | --- | --- | --- | --- |
| `model_size_billions` | B | Parsed or fallback model scale in billions of parameters. | `parse(model.parameters.declared_size \|\| model.parameters.size) \|\| fallback(model.name)` | `model.name`, `model.parameters.declared_size`, `model.parameters.size`, `agentminmax/data/model_sizes.json` |
| `active_model_size_billions` | B | Activated parameters per token when known; unknown when no active-size estimate is available. | `fallback(model.name).active_parameter_billions \|\| unknown` | `model.name`, `agentminmax/data/model_sizes.json` |
| `model_absorption` | ratio | Estimated share of task complexity absorbed by model scale. | `piecewise(model.size_billions)` | `model.size_billions` |

### Complexity

- Group id: `complexity`
- Dashboard display: `histogram`

| Metric | Unit | Meaning | Formula | Inputs |
| --- | --- | --- | --- | --- |
| `intrinsic_score` | score | Task complexity before model absorption. | `log1p(tokens.total)/2 + 1.35*tool_calls + 0.55*unique_tools + benchmark/task/code/time terms` | `token.input`, `token.output`, `tool.call`, `benchmark.task_result`, `code.lines_changed`, `duration_seconds` |
| `effective_score` | score | Complexity remaining after model absorption. | `complexity.intrinsic_score * (1 - model.absorption)` | `complexity.intrinsic_score`, `model.absorption` |
| `chaos_score` | score | Proxy for failed benchmarks, deletion churn, and quality gap. | `failed_benchmarks + 0.01*code.lines_deleted + 0.25*quality_gap` | `benchmark.task_result.completed`, `code.lines_deleted`, `benchmark.task_result.quality_score` |
| `recommended_grain` | class | Recommended agent goal grain from effective complexity score. | `bucket(complexity.effective_score)` | `complexity.effective_score` |

### Intent And Grain

- Group id: `intent`
- Dashboard display: `cards`

| Metric | Unit | Meaning | Formula | Inputs |
| --- | --- | --- | --- | --- |
| `intent_kind` | class | Heuristic task intent from prompt and artifacts. | `heuristic(logs, code.lines_changed, benchmark.task_result)` | `message.content`, `code.lines_changed`, `benchmark.task_result` |
| `expected_artifact` | class | Likely output artifact type. | `heuristic(intent_kind, code.lines_changed, benchmark.task_result)` | `metric.intent_kind`, `code.lines_changed`, `benchmark.task_result` |
| `model_normalized_grain` | score | Complexity remaining after model absorption. | `complexity.effective_score` | `complexity.effective_score`, `model.parameters.declared_size` |

### LLM Runtime

- Group id: `llm`
- Dashboard display: `cards`

| Metric | Unit | Meaning | Formula | Inputs |
| --- | --- | --- | --- | --- |
| `context_utilization` | ratio | Input tokens divided by declared context window. | `token.input / model.context_window` | `token.input`, `model.context_window` |
| `input_output_expansion_ratio` | ratio | Output tokens divided by input tokens. | `token.output / token.input` | `token.output`, `token.input` |
| `cache_hit_ratio` | ratio | Cached input tokens divided by input tokens. | `token.cached_input / token.input` | `token.cached_input`, `token.input` |
| `tokens_per_second` | tokens/s | Total tokens divided by wall-clock duration. | `(token.input + token.output) / duration_seconds` | `token.input`, `token.output`, `duration_seconds` |

### Tools And Calls

- Group id: `agent_behavior`
- Dashboard display: `bars`

| Metric | Unit | Meaning | Formula | Inputs |
| --- | --- | --- | --- | --- |
| `tool_call_count` | calls | Total tool calls. | `sum(tool.call)` | `tool.call` |
| `unique_tool_count` | tools | Distinct tool names used. | `count(distinct tool.call.tool)` | `tool.call` |
| `tool_error_count` | calls | Tool trace events with error status. | `count(trace.tool where status=error)` | `trace.tool.status`, `trace.tool.summary`, `trace.tool.output` |
| `tool_success_rate` | ratio | Tool calls not associated with observed error traces. | `(tool_call_count - tool_error_count) / tool_call_count` | `metric.tool_call_count`, `metric.tool_error_count` |
| `retry_ratio` | ratio | Repeated tool calls divided by total tool calls. | `sum(max(tool_count - 1, 0)) / tool_call_count` | `tool.call` |
| `patch_failure_count` | failures | Observed patch verification or patch_apply_end failures. | `count(patch trace failures)` | `trace.patch.status`, `trace.patch.summary`, `trace.patch.output` |

### Planning

- Group id: `planning`
- Dashboard display: `cards`

| Metric | Unit | Meaning | Formula | Inputs |
| --- | --- | --- | --- | --- |
| `plan_update_count` | updates | Observed update_plan events from tools and traces. | `max(tool.update_plan, count(trace.update_plan))` | `tool.update_plan`, `trace.update_plan` |
| `plan_churn_proxy` | ratio | Plan update count divided by maximum observed plan width. | `plan_update_count / max(len(trace.update_plan.plan))` | `metric.plan_update_count`, `trace.update_plan.args.plan` |

### DAG And Plan Shape

- Group id: `dag`
- Dashboard display: `cards`

| Metric | Unit | Meaning | Formula | Inputs |
| --- | --- | --- | --- | --- |
| `dag_width_proxy` | items | Maximum observed plan item count as a DAG width proxy. | `max(len(trace.update_plan.plan))` | `trace.update_plan.args.plan` |
| `leaf_pending_ratio` | ratio | Pending plan leaves divided by maximum observed plan width. | `pending(latest_plan) / dag_width_proxy` | `trace.update_plan.args.plan`, `metric.dag_width_proxy` |

### Chaos Signals

- Group id: `chaos`
- Dashboard display: `cards`

| Metric | Unit | Meaning | Formula | Inputs |
| --- | --- | --- | --- | --- |
| `tool_entropy` | bits | Shannon entropy of tool-call distribution. | `-sum(p(tool) * log2(p(tool)))` | `tool.call` |
| `error_pressure` | ratio | Tool errors divided by total tool calls. | `tool_error_count / tool_call_count` | `metric.tool_error_count`, `metric.tool_call_count` |

### Local Optimum Signals

- Group id: `local_optimum`
- Dashboard display: `cards`

| Metric | Unit | Meaning | Formula | Inputs |
| --- | --- | --- | --- | --- |
| `exploration_to_edit_ratio` | ratio | Read/search tool calls divided by edit tool calls. | `read_search_tool_calls / edit_tool_calls` | `tool.call` |
| `effective_output_density` | lines/call | Changed lines divided by total tool calls. | `code.lines_changed / tool_call_count` | `code.lines_changed`, `metric.tool_call_count` |
| `local_optimum_signal` | score | Composite proxy for low-quality high-exploration local iteration. | `((1 - benchmark_quality) + min(exploration_edit_ratio / 10, 1) + min(retry_ratio, 1)) / 3` | `metric.benchmark_quality`, `metric.exploration_to_edit_ratio`, `metric.retry_ratio` |

### Engineering Output

- Group id: `engineering`
- Dashboard display: `cards`

| Metric | Unit | Meaning | Formula | Inputs |
| --- | --- | --- | --- | --- |
| `files_changed` | files | Files changed by structured code metrics. | `code.files_changed` | `code.files_changed` |
| `lines_changed` | lines | Added plus deleted lines. | `code.lines_added + code.lines_deleted` | `code.lines_added`, `code.lines_deleted` |
| `churn_proxy` | ratio | Deleted lines divided by total changed lines. | `code.lines_deleted / code.lines_changed` | `code.lines_deleted`, `code.lines_changed` |
| `test_pass_rate` | ratio | Passed benchmark tests divided by total tests. | `sum(benchmark.tests_passed) / sum(benchmark.tests_total)` | `benchmark.tests_passed`, `benchmark.tests_total` |

### Benchmark Signals

- Group id: `benchmark`
- Dashboard display: `cards`

| Metric | Unit | Meaning | Formula | Inputs |
| --- | --- | --- | --- | --- |
| `benchmark_result_count` | tasks | Task-level benchmark result count. | `count(benchmark.task_result)` | `benchmark.task_result` |
| `benchmark_completion_rate` | ratio | Completed benchmark tasks divided by result count. | `count(completed benchmark.task_result) / count(benchmark.task_result)` | `benchmark.task_result.completed` |
| `benchmark_quality` | score | Average task quality score. | `mean(benchmark.task_result.quality_score)` | `benchmark.task_result.quality_score` |

## Benchmark Metric Groups

### Benchmark Quality

- Group id: `benchmark_quality`
- Dashboard display: `bars`

| Metric | Unit | Meaning | Formula | Inputs |
| --- | --- | --- | --- | --- |
| `pass_rate` | ratio | Completed tasks divided by total benchmark results. | `run.completed_count / run.task_count` | `run.completed_count`, `run.task_count` |
| `average_quality_score` | score | Mean quality score over task results. | `mean(benchmark_result.quality_score)` | `benchmark_result.quality_score` |
| `completed_count` | tasks | Completed benchmark tasks. | `sum(benchmark_result.completed)` | `benchmark_result.completed` |
| `task_count` | tasks | Distinct task count. | `count(distinct benchmark_result.task_id)` | `benchmark_result.task_id` |

### Benchmark Cost

- Group id: `benchmark_cost`
- Dashboard display: `bars`

| Metric | Unit | Meaning | Formula | Inputs |
| --- | --- | --- | --- | --- |
| `tokens_per_task` | tokens/task | Total tokens divided by task count. | `run.total_tokens / run.task_count` | `run.total_tokens`, `run.task_count` |
| `tool_calls_per_task` | calls/task | Tool calls divided by task count. | `run.total_tool_calls / run.task_count` | `run.total_tool_calls`, `run.task_count` |
| `duration_per_task` | seconds/task | Wall-clock seconds divided by task count. | `run.total_duration_seconds / run.task_count` | `run.total_duration_seconds`, `run.task_count` |
| `lines_changed_per_task` | lines/task | Changed lines divided by task count. | `run.total_lines_changed / run.task_count` | `run.total_lines_changed`, `run.task_count` |
| `cost_per_pass` | tokens/pass | Total tokens divided by completed tasks. | `run.total_tokens / run.completed_count` | `run.total_tokens`, `run.completed_count` |
| `sessions_per_task` | sessions/task | Contributing sessions divided by task count. | `run.session_count / run.task_count` | `run.session_count`, `run.task_count` |

### Benchmark Stability

- Group id: `benchmark_stability`
- Dashboard display: `cards`

| Metric | Unit | Meaning | Formula | Inputs |
| --- | --- | --- | --- | --- |
| `completion_variance_proxy` | variance | Bernoulli variance proxy from benchmark completion rate. | `pass_rate * (1 - pass_rate)` | `metric.pass_rate` |
| `average_tokens_per_session` | tokens/session | Total tokens divided by contributing sessions. | `run.total_tokens / run.session_count` | `run.total_tokens`, `run.session_count` |
| `depth_cost_proxy` | calls/session | Tool calls divided by contributing sessions. | `run.total_tool_calls / run.session_count` | `run.total_tool_calls`, `run.session_count` |

## Regeneration

Run `python scripts/generate_observability_docs.py` from the repository root with `doxygen` available on PATH. The command first invokes Doxygen with `docs/observability/Doxyfile`, then rewrites this Markdown file from the code-level event and metric definitions.
