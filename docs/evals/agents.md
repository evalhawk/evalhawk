# Agents

!!! info "Planned: Phase 4 (final outcomes and repeats); later (tool calls and steps)"

## What it covers

Systems that take **several steps** to finish a task: calling tools, searching, planning,
writing and running code, booking or updating things.

There are two levels of testing, and EvalHawk builds them in this order:

| Level | Question | Available |
|---|---|---|
| **Outcome** | Did the agent end up with the right result? | Phase 4 |
| **Steps** | Did it get there sensibly: right tools, right arguments, no wasted steps? | Later |

## What can go wrong

| Level | Failure | Example |
|---|---|---|
| Outcome | Task not done | Says "booked!" but no booking exists |
| Outcome | Wrong result | Books the most expensive flight instead of the cheapest |
| Outcome | **Inconsistent** | Succeeds 3 times out of 5 on the same task |
| Steps | Wrong tool or arguments | Calls `refund(amount=590)` instead of `59.0` |
| Steps | Wasted effort | Twelve searches for a one-step task |

## Outcome evals (Phase 4)

EvalHawk treats the agent as a **black box**: a task goes in, a final result comes out.
If your agent can be called as a Python function or an HTTP endpoint, it can be tested.

| Eval | Question it asks | How it works | Needs | Based on |
|---|---|---|---|---|
| `task_completed` | Did the agent complete the task? | AI judge reads the task and the final result; or a code check against the known expected outcome | `input`, `output` (+ `reference`) | Task-success judging |
| Custom questions | e.g. "Did it confirm with the user before paying?" | AI judge | `input`, `output` | G-Eval, made binary |
| Code checks on the result | e.g. "Is the booking ID present?", "Is the final state correct?" | Code | `output`, `reference` | — |

### Repeats: the agent-specific feature

Agents are **random**. The same task can succeed on one run and fail on the next, so a
single run tells you little. Set `repeats`:

```toml
[evaluations.booking_agent]
repeats = 5        # every task runs 5 times
```

EvalHawk then reports:

- **success rate** with an error range that treats the 5 runs of one task as **related**,
  not as 5 independent tests. Most tools skip this and look far more certain than they are.
- **pass^k**: the share of tasks that succeed on **all** k runs. It measures reliability,
  from [τ-bench](https://arxiv.org/abs/2406.12045) (Yao et al., 2024).

```text
task_completed   64%  [55% – 72%]   100 tasks × 5 runs    (clustered by task)
pass^5           38%  [29% – 48%]   succeeded on all 5 runs
```

The gap between 64% and 38% is the agent's unreliability, which is often the most
important number for a production agent.

## Step evals (later)

When your trace records the agent's tool calls, these checks become possible:

| Eval | Question it asks | How it works | Based on |
|---|---|---|---|
| `tool_selected` | Was the expected tool called? | Code, comparing with expected calls | [Berkeley Function-Calling Leaderboard](https://gorilla.cs.berkeley.edu/leaderboard.html) (AST-based checking) |
| `tool_arguments` | Were the arguments correct? | Code: parse and compare arguments | Same |
| `step_efficiency` | Were there unnecessary steps? | AI judge over the whole trace | — |

## What you provide

```json
{"input": "Book the cheapest direct flight from London to Paris on 12 May for 1 adult", "reference": {"flight": "BA304"}}
```

The agent's final answer (and, later, its tool-call trace) comes back through the target.

## How it's tested

1. Each task is sent to your agent `repeats` times; runs are grouped by task.
2. Outcome criteria are checked on each run (code checks instantly; AI criteria judged and cached).
3. You label a sample of runs as done / not done, blind.
4. The report shows the corrected success rate, pass^k, and the judge's report card.
5. `evalhawk compare` tells you whether a new agent version is genuinely more reliable.

## Example config

```toml
[target]
type    = "http"
url     = "https://agent.internal/run"
body    = '{"task": "{{input}}"}'
answer_path = "$.final_answer"
timeout = 300                      # agents are slow

[[criteria]]
id       = "task_completed"
question = "Did the agent fully complete the task described in the input?"

[evaluations.booking_agent]
dataset  = "data/booking_tasks.jsonl"
kind     = "single_turn"
repeats  = 5
criteria = { task_completed = "local" }

[runner]
max_concurrency = 4
max_cost_usd    = 5.00
```

## Compared with DeepEval

| | DeepEval | EvalHawk |
|---|---|---|
| Outcome | Task Completion | `task_completed` + corrected rate + error range |
| Randomness | Not handled statistically | `repeats`, clustered error ranges, pass^k |
| Steps | Tool Correctness, Argument Correctness, Step Efficiency, Plan Adherence, Plan Quality | Later |
