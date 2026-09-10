# 🧬 Kodex — Autonomous Self-Healing Codebase Agent

<div align="center">

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Groq](https://img.shields.io/badge/LLM_Engine-Groq-f55036.svg)](https://groq.com/)
[![LangGraph](https://img.shields.io/badge/Orchestration-LangGraph-orange.svg)](https://github.com/langchain-ai/langgraph)
[![Qdrant](https://img.shields.io/badge/Vector_DB-Qdrant-red.svg?logo=qdrant&logoColor=white)](https://qdrant.tech/)
[![Streamlit](https://img.shields.io/badge/UI-Streamlit-FF4B4B.svg?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Docker](https://img.shields.io/badge/Sandbox-Docker-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com/)

**An intelligent, multi-agent AI system that detects errors, understands project context via RAG, writes verified code fixes in a sandbox, and heals codebases automatically.**

[Key Features](#-key-features) • [Architecture](#-architecture) • [Getting Started](#-getting-started) • [Usage](#-usage) • [Configuration](#-configuration) • [Project Structure](#-project-structure)

</div>

---

## 📖 Overview

**Kodex** is a production-grade autonomous agent built to eliminate repetitive debugging and fixing workflows. When code breaks—whether due to syntax errors, linting issues (via Ruff), or failing test suites (via Pytest)—Kodex steps in:

1. **Detects** bugs and test failures.
2. **Retrieves** relevant context across the entire repository using AST-aware code search with **LlamaIndex** and **Qdrant**.
3. **Reasons** about the root cause and generates minimal, precise patches with **LangGraph** orchestration.
4. **Validates** patches in an isolated **Docker Sandbox** before applying them to your workspace.
5. **Maintains safety** through automatic Git branching, rollbacks, and optional **Human-in-the-Loop Review Mode**.

---

## ✨ Key Features

- 🔄 **Autonomous Self-Healing Loop**: Continuous cycle of error detection, RAG retrieval, patch generation, sandbox testing, and git committing until the build is green or retry limits are reached.
- 🧠 **Codebase-Aware RAG Engine**: Indexes code repositories into Qdrant vector store. Resolves multi-file references, imports, and cross-file dependencies so patches don't introduce regressions.
- 🐳 **Isolated Docker Sandbox**: Runs untrusted code, tests, and linters inside isolated containers (`kodex-sandbox`) to protect your host system. Automatically falls back to safe local execution if Docker is unavailable.
- 🛡️ **Human-in-the-Loop Review**: Choose between `--mode auto` for hands-off autonomous fixing or `--mode review` to inspect, approve, or reject patches via the Streamlit UI.
- 📊 **Streamlit Command Center**: Full-featured interactive dashboard featuring real-time terminal logs, side-by-side syntax-highlighted diff viewers, session replays, and audit report exports.
- 📈 **Observability & Cost Tracking**: Detailed token usage and dollar cost tracking per fix, SQLite-backed session persistence, and comprehensive Markdown audit reports.
- 🔌 **Extensible Tool Registry**: Customize or plug in new tools (linters, test runners, custom scripts) simply by updating `tools_config.yaml`.

---

## 🏗️ Architecture

```mermaid
flowchart TD
    subgraph Input ["Codebase Input"]
        Repo[Source Code Repository]
    end

    subgraph Agent ["LangGraph Orchestrator"]
        Detect[1. Detect Errors / Run Tests]
        RAG[2. Multi-File RAG Context Retrieval]
        Plan[3. LLM Reasoning & Patch Generation]
        Review{Human Review Mode?}
        UserApprove[User Approves / Modifies]
        Verify[4. Docker Sandbox Verification]
        Commit[5. Git Commit / Rollback]
    end

    subgraph Infrastructure ["Under the Hood"]
        Qdrant[(Qdrant Vector DB)]
        Sandbox[[Docker Container Sandbox]]
        Store[(SQLite Session Store & Token Tracker)]
    end

    Repo --> Detect
    Detect -->|Errors Found| RAG
    Qdrant <-->|Context & Embeddings| RAG
    RAG --> Plan
    Plan --> Review
    Review -->|Yes| UserApprove
    UserApprove --> Verify
    Review -->|No (Auto)| Verify
    Sandbox <-->|Run pytest / ruff| Verify
    Verify -->|Pass| Commit
    Verify -->|Fail & Retries Left| Plan
    Commit --> Store
```

---

## 🚀 Getting Started

### Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| **Python** | `3.10+` | Core agent runtime |
| **Git** | `2.30+` | Version control & patch tracking |
| **Docker Desktop** | Latest *(Optional)* | Secure sandbox & Qdrant container |
| **Groq API Key** | Free tier / paid | Ultra-fast LLM reasoning (`llama-3.3-70b`) |

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/shivamkolpyakwar/Kodex.git
   cd Kodex
   ```

2. **Create and activate a virtual environment**:
   ```bash
   # Linux / macOS
   python3 -m venv .venv
   source .venv/bin/activate

   # Windows
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**:
   ```bash
   cp .env.example .env
   ```
   Open `.env` and add your Groq API key:
   ```env
   GROQ_API_KEY=gsk_your-groq-api-key-here
   GROQ_MODEL=llama-3.3-70b-versatile
   ```

5. **Start Services (Docker)**:
   ```bash
   # Start Qdrant vector database
   docker-compose up -d qdrant

   # Build sandbox container
   docker-compose build sandbox
   ```
   > **Note**: If Docker is not installed or running, Kodex will automatically fall back to an in-memory vector store and local execution.

---

## 💻 Usage

### 1. Launch the Streamlit Command Center (Recommended)

Start the graphical dashboard for real-time visualization, human-in-the-loop review, and diff inspection:

```bash
# Direct launch
streamlit run kodex/ui/app.py

# Or via CLI helper
python -m kodex.main ui
```

Access the UI at `http://localhost:8501`.

### 2. CLI Mode

#### Index a Repository
Index your codebase into Qdrant for RAG semantic search:
```bash
python -m kodex.main index /path/to/your/project
```

#### Run Autonomous Healing (Auto Mode)
Scan, diagnose, patch, verify, and commit fixes automatically:
```bash
python -m kodex.main heal /path/to/your/project --mode auto --index --report
```

#### Run with Human Review (Review Mode)
Pause after patch generation to inspect and approve diffs before applying:
```bash
python -m kodex.main heal /path/to/your/project --mode review --index
```

#### CLI Options
```text
usage: kodex heal [-h] [--mode {auto,review}] [--max-retries N]
                  [--index] [--report] [--log-level LEVEL] repo

positional arguments:
  repo                  Path to the target repository

options:
  --mode {auto,review}  Agent mode (default: auto)
  --max-retries N       Max fix retries per error (default: 3)
  --index               Index the repository before healing
  --report              Generate Markdown audit report after completion
  --log-level LEVEL     Logging level (DEBUG, INFO, WARNING, ERROR)
```

---

## ⚙️ Configuration

Kodex is configured via environment variables in `.env` and tool settings in `tools_config.yaml`.

### Key `.env` Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `GROQ_API_KEY` | `""` | Groq API key for ultra-fast reasoning (required) |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | High-speed LLM model on Groq |
| `OPENAI_API_KEY` | `""` | Optional fallback or for OpenAI embeddings |
| `QDRANT_URL` | `http://localhost:6333` | URL of Qdrant vector database |
| `SANDBOX_IMAGE` | `kodex-sandbox:latest` | Docker image tag for code sandbox |
| `AGENT_MODE` | `auto` | Default operating mode (`auto` or `review`) |
| `MAX_RETRIES` | `3` | Maximum attempts to fix a failing test/lint error |
| `AUTO_COMMIT` | `true` | Automatically commit verified fixes to Git |

---

## 📂 Project Structure

```
Kodex/
├── kodex/
│   ├── agent/                 # LangGraph state machine & node logic
│   │   ├── graph.py           # StateGraph builder and workflow edges
│   │   ├── nodes.py           # Error detection, reasoning, patching nodes
│   │   └── state.py           # Typed agent state definition
│   ├── rag/                   # Repository indexing and retrieval
│   │   ├── engine.py          # LlamaIndex + Qdrant connector
│   │   ├── indexer.py         # Code chunking & vector indexing
│   │   └── retriever.py       # Cross-file context retrieval
│   ├── sandbox/               # Containerized execution environment
│   │   └── docker_sandbox.py  # Docker SDK runner with local fallback
│   ├── tools/                 # Dynamic tool execution registry
│   │   ├── file_tool.py       # File reading, writing, and patching
│   │   ├── git_tool.py        # Branching, diffing, and committing
│   │   ├── lint_tool.py       # Ruff linter runner
│   │   ├── registry.py        # YAML-driven tool registry
│   │   ├── sandbox_tool.py    # Sandbox lifecycle tool
│   │   └── test_tool.py       # Pytest test execution tool
│   ├── tracking/              # Observability, metrics, and persistence
│   │   ├── audit_logger.py    # SQLite audit event logging
│   │   ├── report_generator.py# Markdown audit report builder
│   │   ├── session_store.py   # Run session storage & history
│   │   └── token_tracker.py   # Token count & cost estimator
│   ├── ui/                    # Streamlit Command Center
│   │   ├── app.py             # Streamlit application entry point
│   │   ├── components/        # Dashboard, diff viewer, terminal components
│   │   └── styles/            # Custom UI CSS and themes
│   ├── config.py              # Pydantic settings management
│   └── main.py                # Command-line interface entry point
├── tests/                     # Unit and integration test suites
│   ├── test_agent.py          # Agent state and node tests
│   ├── test_rag.py            # RAG indexing and search tests
│   ├── test_sandbox.py        # Docker sandbox tests
│   └── test_tools.py          # Tool registry tests
├── Dockerfile.sandbox         # Container definition for isolated execution
├── docker-compose.yml         # Qdrant and sandbox compose services
├── tools_config.yaml          # Tool definitions and parameters
├── requirements.txt           # Python package dependencies
├── setup_guide.md             # Detailed local development guide
└── LICENSE                    # MIT License
```

---

## 🧪 Testing

Run test suites using pytest:

```bash
# Run all tests
pytest

# Run tests with verbose output
pytest -v

# Run a specific module
pytest tests/test_agent.py
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE) — see the LICENSE file for details.

---

<div align="center">
Built by <b>Shivam Kolpyakwar</b>
</div>
