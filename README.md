# AgentBench

> An automated benchmark framework designed for [OpenAgent](https://github.com/the-open-agent/openagent), covering four dimensions: performance baseline, dialogue quality, complex long-horizon tasks, and tool invocation. It enables fast, quantitative evaluation of agent performance.

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)

---

## Table of Contents

- [Overview](#overview)
- [Core Features](#core-features)
- [Benchmark Dimensions](#benchmark-dimensions)
- [Quick Start](#quick-start)
- [CLI Arguments](#cli-arguments)
- [Project Structure](#project-structure)
- [Datasets](#datasets)
- [Reading Reports](#reading-reports)
- [Extending AgentBench](#extending-agentbench)
- [System Requirements](#system-requirements)
- [Security & Privacy](#security--privacy)
- [License](#license)

---

## Overview

AgentBench is a lightweight benchmark framework for the OpenAgent ecosystem. Through standardized datasets, reproducible test workflows, and automated report generation, it helps developers:

- **Quantify performance**: obtain key metrics such as latency, token consumption, and success rate.
- **Validate correctness**: check output format, factual accuracy, and instruction-following fidelity.
- **Evaluate tool invocation**: verify output quality and evidence completeness in tool-calling scenarios (e.g. `web_search`, `shell`, `browser_use`).
- **Stress-test long-horizon tasks**: exercise deep reasoning and structured-output capabilities via multi-stage complex prompts.

The framework relies solely on the Python standard library (with only optional `PyYAML` for legacy dataset support), making it plug-and-play and easy to integrate into CI/CD pipelines.

---

## Core Features

| Feature | Description |
|---------|-------------|
| **Four benchmark suites** | `baseperf` (performance baseline), `dialogue` (dialogue quality), `hardchat` (complex long-horizon tasks), `tool` (tool invocation validation) |
| **Multi-round & retry** | Supports `--rounds` multi-round testing and `--max-attempts` retry on failure for more stable results |
| **Automated reports** | Each run auto-generates `report.md`, `summary.json`, and `details.jsonl`, including a 95% Bootstrap confidence interval |
| **Server-side log verification** | For the Tool suite, optionally cross-checks invocation traces against OpenAgent server logs |
| **Zero-config out-of-the-box** | Rich built-in datasets; launch a full benchmark with a single command |
| **Extensible architecture** | Add new benchmark dimensions easily via the `SuiteBase` abstract base class |

---

## Benchmark Dimensions

### 1. BasePerf (Performance Baseline)

- **Goal**: test basic OpenAgent availability, response latency, and token consumption.
- **Dataset**: `datasets/baseperf/dataset.jsonl`
- **Validation logic**: verify HTTP response success, valid JSON parsing, and non-empty assistant output.
- **Output metrics**: success rate, average latency, token mean / standard deviation.

### 2. Dialogue (Dialogue Quality)

- **Goal**: validate format compliance, factual accuracy, and instruction understanding.
- **Dataset**: `datasets/dialogue/dataset.jsonl`
- **Validation logic**:
  - **Format check**: require JSON Object / JSON Array output with mandatory fields.
  - **Fact matching**: verify key information via regular expressions.
  - **Instruction following**: check character count, word count, line prefix, forbidden words, etc.
- **Typical tasks**: JSON formatting, factual Q&A, translation, text rewriting.

### 3. HardChat (Complex Long-Horizon Tasks)

- **Goal**: test the agent's ability to handle high-complexity, multi-stage prompts with strict structured JSON output.
- **Dataset**: `datasets/hardchat/tasks.jsonl`
- **Validation logic**: verify that the returned JSON contains the three required stage fields (`collect`, `normalize`, `summarize`).
- **Typical tasks**:
  - Deep web research and synthesis reports (WebSearch Synthesis)
  - In-depth RFC technical document analysis and comparison
  - Shell environment diagnostics and governance blueprints
  - Browser-based multi-step information workflows

### 4. Tool (Tool Invocation Validation)

- **Goal**: verify that the agent can produce structured output conforming to specifications in tool-calling scenarios, and present a complete evidence chain.
- **Dataset**: `datasets/tool/dataset.jsonl`
- **Validation logic**:
  - Validate mandatory JSON fields (e.g. `task_id`, `claims`, `evidence.tool_calls`).
  - Check that required tool names appear in `evidence.tool_calls`.
  - **(Optional) Server-side log verification**: scan OpenAgent's `openagent.log` and console output to cross-check invocation traces.
- **Covered tool types**: `web_search`, `web_fetch`, `shell`, `local_text_write`, `browser_use_open`, `browser_use_snapshot`, etc.

---

## Quick Start

### Prerequisites

Ensure Python >= 3.10 is installed.

**Option 1: Direct install (recommended)**

```bash
# Clone the repository
git clone https://github.com/the-open-agent/agentbench.git
cd agentbench

# Install optional dependency (PyYAML for legacy HardChat YAML datasets)
pip install -r requirements.txt
```

**Option 2: Docker**

```bash
# Build the image
docker build -t agentbench .

# Run the benchmark (point to your OpenAgent instance)
docker run --rm agentbench \
  --base-url http://host.docker.internal:14000 \
  --provider-key $OPENAGENT_PROVIDER_KEY
```

### Start OpenAgent

AgentBench sends requests to `http://127.0.0.1:14000` by default. Make sure your OpenAgent service is running and listening on that address.

### Run the benchmark

```bash
# Run all suites (recommended for first use)
python -m agentbench run \
  --base-url http://127.0.0.1:14000 \
  --model deepseek/deepseek-v4-flash \
  --provider-key $OPENAGENT_PROVIDER_KEY \
  --rounds 3 \
  --max-attempts 2 \
  --timeout 240

# Run only the tool invocation suite
python -m agentbench run --suite tool --provider-key $OPENAGENT_PROVIDER_KEY

# Run only the dialogue quality suite
python -m agentbench run --suite dialogue --provider-key $OPENAGENT_PROVIDER_KEY
```

> **Tip**: `--provider-key` can also be passed via the `OPENAGENT_PROVIDER_KEY` environment variable to avoid exposing secrets on the command line.

### View results

After the run completes, the terminal will print something like:

```text
Session written to: results/session-20260512-143052-a1b2c3d4
```

Navigate into that directory to inspect the outputs:

```text
session-20260512-143052-a1b2c3d4/
├── meta.json          # Test metadata (config, health check, timestamp)
├── summary.json       # Aggregated stats (success rate, latency, tokens, top-10 failure reasons)
├── details.jsonl      # Detailed record of every request
├── report.md          # Human-readable comprehensive report
├── baseperf/
│   ├── report.md
│   ├── summary.json
│   └── details.jsonl
├── dialogue/
│   └── ...
├── hardchat/
│   └── ...
└── tool/
    └── ...
```

---

## CLI Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `command` | `run` | Subcommand; currently only `run` is supported |
| `--suite` | `all` | Select benchmark suite: `baseperf`, `dialogue`, `hardchat`, `tool`, `all` |
| `--base-url` | `http://127.0.0.1:14000` | OpenAgent service URL |
| `--model` | `deepseek/deepseek-v4-flash` | Model name |
| `--provider-key` | `$OPENAGENT_PROVIDER_KEY` | API key |
| `--rounds` | `3` | Number of rounds per task |
| `--max-attempts` | `2` | Maximum retries after a single-round failure |
| `--timeout` | `240` | Per-request timeout in seconds |

---

## Project Structure

```text
agentbench/
├── benchcore/                  # Core engine
│   ├── runner.py               # Benchmark main loop (health check → multi-round execution → result aggregation)
│   ├── models.py               # Data models: RunContext, RunRecord, SuiteResult
│   ├── http_client.py          # HTTP client (health_check, post_json)
│   ├── reporting.py            # Report generation (Markdown + JSON + JSONL)
│   ├── stats.py                # Statistics utilities (mean, std, Bootstrap 95% CI)
│   └── utils.py                # Common utilities (JSON read/write, timestamps, JSON parsing fallback)
├── suites/                     # Benchmark suite implementations
│   ├── base.py                 # Abstract base class SuiteBase
│   ├── baseperf.py             # Performance baseline suite
│   ├── dialogue.py             # Dialogue quality suite
│   ├── hardchat.py             # Complex long-horizon task suite
│   ├── tool.py                 # Tool invocation validation suite
│   ├── easychat_common.py      # Shared logic for BasePerf / Dialogue
│   └── openagent_log_verify.py # OpenAgent server-side log cross-check
├── datasets/                   # Built-in datasets
│   ├── baseperf/dataset.jsonl
│   ├── dialogue/dataset.jsonl
│   ├── hardchat/tasks.jsonl
│   └── tool/dataset.jsonl
├── cli.py                      # CLI entry point
├── __main__.py                 # `python -m agentbench` entry point
├── requirements.txt            # Python dependencies
├── pyproject.toml              # Project metadata and packaging config
├── Dockerfile                  # Docker build file
├── .gitignore                  # Git ignore rules
├── .dockerignore               # Docker build ignore rules
├── LICENSE                     # Apache 2.0 license
└── README.md                   # This file
```

---

## Datasets

All datasets use the **JSON Lines** format (one JSON object per line) for easy streaming and extension.

| Dataset | Tasks | Categories | Description |
|---------|-------|------------|-------------|
| `baseperf` | 40 | format / factual / instruction / readability / completion | Covers JSON formatting, factual Q&A, instruction following, text rewriting, and completion tasks |
| `dialogue` | 32 | format / factual / instruction / readability | Split from baseperf; focused on dialogue quality evaluation |
| `hardchat` | 6 | web_search / web_fetch / shell / file_ops / browser / mixed | High-difficulty long-horizon tasks requiring multi-stage structured output |
| `tool` | 12 | WebSearch / WebFetch / Shell / File / Browser / Mixed | Validates structured output and evidence-chain completeness in tool-calling scenarios |

Some `tool` tasks use relative paths (e.g. `./scratch/`, `./openagent/logs/`). Create the corresponding directories in the current working directory before running, or modify the paths in `datasets/tool/dataset.jsonl` to suit your environment.

### Custom datasets

You can directly edit `datasets/<suite>/dataset.jsonl`. The `tool` suite uses a single `datasets/tool/dataset.jsonl` (one task per line). For backward compatibility, the runtime also supports the legacy `tasks_index.json` + `tasks/*.json` fallback loading pattern.

---

## Reading Reports

### Success Rate

Represents the proportion of tasks across all rounds that passed validation for a given suite. The report also includes a **95% Bootstrap confidence interval** to help assess statistical significance.

### Latency

- **mean**: average response latency in milliseconds
- **std**: latency variability
- **worst**: worst-case latency

### Token Consumption

- **mean / std**: average and standard deviation, useful for cost and model-efficiency assessment.

### Top 10 Failure Reasons

Aggregates the most common failure types, for example:

- `empty_response`: empty content returned
- `json_format_invalid`: JSON parsing failed
- `missing_key:xxx`: a mandatory field is missing
- `fact_pattern_missing:xxx`: factual pattern match failed
- `max_chars_exceeded`: response character count exceeds the `max_chars` limit specified in the task (dialogue tasks)
- `missing_tool_call:...`: the required tool name is not declared in `evidence.tool_calls` (or root-level `tool_calls`); the validator recognizes `name` / `tool` / `function.name` and dot-prefixed tool IDs.

---

## Extending AgentBench

### Adding a new benchmark suite

1. Create a new file under `suites/` that inherits from `SuiteBase`:

```python
from .base import SuiteBase
from ..benchcore.models import RunRecord

class MySuite(SuiteBase):
    name = "mysuite"

    def load_tasks(self) -> list[dict]:
        # Load your dataset
        return [...]

    def run_task(self, task, round_index, attempt, base_url, model, provider_key, timeout_s) -> RunRecord:
        # Implement evaluation logic
        return RunRecord(...)
```

2. Register it in `cli.py` under `suite_map`:

```python
from .suites.mysuite import MySuite

suite_map = {
    ...
    "mysuite": MySuite(root),
}
```

3. Run:

```bash
python -m agentbench run --suite mysuite
```

### Customizing statistics and reports

- `benchcore/stats.py`: customize statistical methods (e.g. swap the confidence-interval algorithm).
- `benchcore/reporting.py`: modify the Markdown report template or add new output formats.

---

## System Requirements

| Item | Requirement |
|------|-------------|
| Python | >= 3.10 |
| OS | Windows, Linux, macOS |
| Network | Must be able to reach the OpenAgent service address |

> **Cross-platform note**: AgentBench core code depends only on the Python standard library. All path operations use `pathlib`, and HTTP requests use the standard-library `urllib`, so it runs correctly on Windows, Linux, and macOS.

## Security & Privacy

- **Never** commit API keys, cookies, internal URLs, or evaluation results containing personal data to the repository; `results/` is already ignored in `.gitignore`.
- Optional console log fallback paths: environment variable `OPENAGENT_CONSOLE_LOG`, or `logs/openagent_console.log` in the current working directory (see `openagent_log_verify.py`).

## License

This project is licensed under the [Apache License 2.0](LICENSE).

---

> **AgentBench** is an important part of the OpenAgent ecosystem. If you discover interesting cases or have improvement suggestions during benchmarking, please open an issue at [agentbench Issues](https://github.com/the-open-agent/agentbench/issues) or submit a PR to help refine the evaluation standards.
