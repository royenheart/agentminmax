# AgentMinMax Initial Research

## Problem

Current agents often split goals with unclear principles. For small tasks, a short list of goals can work. For long-horizon projects, the same model-agent loop often stops at a minimal implementation, then requires repeated human pressure to deepen local quality. A frontend example is typical: the agent satisfies "build the page" with a simple hand-rolled version, but achieving a strong visual result may require exploring a heavier charting, animation, layout, or 3D framework.

The failure is not only laziness. It is an interaction among under-specified prompts, sparse evaluation, limited model capability, local greedy choices, and uncontrolled complexity growth.

## Research Position

AgentMinMax studies **complexity-aware control of long-horizon agentic projects**.

The key claim is:

> A large project should be represented as an observable goal graph. Each node needs explicit dependencies, artifacts, evaluation criteria, trace evidence, cost, quality, and relative complexity. The scheduler should minimize global unnecessary complexity, then maximize local depth only at bottleneck nodes where shallow completion has plateaued.

This differs from ordinary task lists. Markdown checklists hide dependency structure, cost, quality, uncertainty, and trace evidence. A graph can show which subproblem blocked quality, which nodes were overworked, and where human feedback changed direction.

## Relation to Existing Work

- ReAct and Reflexion established the loop of reasoning, acting, feedback, and self-correction.
- Tree of Thoughts and Graph of Thoughts showed that model reasoning can benefit from branching or graph-shaped search instead of one linear chain.
- TDP and ReAcTree-style systems move long-horizon work toward scoped subgoals, dynamic trees, and DAG-like decomposition.
- LangGraph, OpenAI Agents SDK tracing, and OpenTelemetry GenAI conventions show that agent execution can be traced with spans, tool calls, model calls, and handoffs.
- SWE-bench Verified, OSWorld, WebArena, VisualWebArena, TheAgentCompany, Terminal-Bench, SWE-smith, and CodeClash show that evaluation is moving from single-turn QA toward long-horizon, environment-grounded, generated, and evolving tasks.
- Frontier-Eng is especially relevant because it studies iterative improvement under executable feedback and reports diminishing returns across rounds, with depth often more valuable than breadth under fixed budget.

## MinMax Principle

The proposed policy is:

1. **Minimize global complexity first.** Build the smallest coherent project graph that satisfies a baseline quality target.
2. **Detect local plateaus.** Measure where repeated edits stop improving quality or increase complexity faster than quality.
3. **Maximize local exploration at bottlenecks.** Spend more search budget on the specific node: try third-party frameworks, generate alternatives, use stronger verifiers, or ask the human for preference feedback.
4. **Collapse successful local work back into the global graph.** Update dependencies, artifacts, quality, and complexity.

This is not pure greed. Pure greed chooses the next easiest visible improvement. AgentMinMax chooses between shrinking, splitting, merging, deepening, or asking for human input based on graph evidence.

## Relative Complexity

Complexity should not be treated as an absolute task property. It is relative to model capability and budget:

```text
EffectiveComplexity = f(TaskComplexity, ModelCapability, Budget, QualityTarget)
```

The same task may require fine-grained decomposition for a 20B model, medium-grained decomposition for a 1T-class model, and coarser semantic nodes for a stronger model. This may change continuously in some regions and discretely at capability thresholds.

Important capability dimensions include:

- Planning depth
- Tool competence
- Context window and long-context reliability
- Code and UI skill
- Visual/design judgment
- Domain familiarity
- Self-evaluation accuracy
- Instruction-following stability
- Cost and latency tolerance

Parameter count is only a proxy. Still, model scale should be recorded because it can explain why the optimal goal grain changes.

## Complexity Metrics

AgentMinMax should track:

- `C_graph`: goal nodes, dependency edges, critical path length, reopened nodes, cycles or repeated splits.
- `C_context`: tokens needed to understand a node, files read, logs consulted, context resets, summarization loss.
- `C_artifact`: files changed, lines changed, dependencies, components, API surface, state count.
- `C_eval`: test count, verifier strength, judge disagreement, human review count.
- `C_search`: number of candidates, branch entropy, repeated attempts, failed local searches.
- `C_chaos`: regressions, graph churn, oscillating decisions, result variance across seeds/models.

The first prototype records a subset: model metadata, tokens, tools, session time, benchmarks, code size, quality, and relative complexity.

## Chaos and "Getting More Confused"

A project is becoming chaotic when quality does not improve while graph, code, context, or search complexity keeps increasing. A practical metric is:

```text
ChaosGrowth = delta(complexity) - k * delta(quality)
```

If `ChaosGrowth` stays positive across several rounds, the agent should stop editing blindly and either decompose, replace the local approach, or ask the human for clarification.

Another useful test is trajectory variance: start multiple agents from the same project state and compare final DAG shape, code structure, quality, and cost. Higher divergence means higher system chaos.

## Research Roadmap

1. Build an observability foundation that captures sessions, model parameters, tokens, tool calls, logs, benchmark outcomes, quality, code scale, and complexity.
2. Add a web dashboard so daily Codex work and benchmark runs can be inspected visually.
3. Normalize results from long-horizon benchmark suites.
4. Add goal DAG capture and replay.
5. Run cross-model experiments to estimate optimal goal grain for 20B, 70B, 1T, 10T-class models.
6. Implement MinMax scheduling policies and compare them against greedy, breadth-first, depth-first, and critical-path baselines.

## First Project Deliverable

The first implementation should be a reusable Codex-oriented observation framework:

- JSONL trace ingestion
- Benchmark result normalization
- Model metadata capture
- Token and tool accounting
- Code size metrics
- Quality and completion metrics
- Relative complexity estimates
- Static web dashboard
- Repo-local Codex plugin scaffold

This creates the measurement layer required before making stronger claims about scheduling or complexity theory.
