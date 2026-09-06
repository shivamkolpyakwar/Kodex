# 🧬 Kodex — Setup Guide

> Step-by-step instructions for setting up the Kodex Self-Healing Codebase Agent on your machine.

---

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.10+ | [python.org](https://www.python.org/downloads/) |
| Git | 2.30+ | [git-scm.com](https://git-scm.com/) |
| Docker Desktop | Latest | [docker.com](https://www.docker.com/products/docker-desktop/) |
| pip | Latest | Comes with Python |

---

## Step 1: Clone the Repository

```bash
git clone https://github.com/shivam-kolpyakwar/Kodex.git
cd Kodex
```

## Step 2: Create a Virtual Environment

```bash
# Create virtual environment
python -m venv .venv

# Activate it
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
```

## Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

## Step 4: Configure Environment Variables

```bash
# Copy the template
cp .env.example .env

# Edit .env with your values
# Required: Set your OpenAI API key
# OPENAI_API_KEY=sk-your-key-here
```

### Getting an OpenAI API Key

1. Go to [platform.openai.com](https://platform.openai.com/)
2. Sign up or log in
3. Navigate to **API Keys** → **Create new secret key**
4. Copy the key and paste it into your `.env` file

## Step 5: Set Up Qdrant (Vector Database)

Qdrant is the vector database that powers Kodex's RAG engine. You need to run it as a Docker container.

```bash
# Start Qdrant
docker-compose up -d qdrant

# Verify it's running
curl http://localhost:6333/healthz
# Should return: {"title":"qdrant - vectorass search engine"}
```

**If Docker is not available**, Kodex will automatically fall back to in-memory mode (data won't persist between sessions).

## Step 6: Build the Sandbox Image

The sandbox is a secure Docker container where Kodex runs linting and tests.

```bash
# Build the sandbox image
docker-compose build sandbox

# Verify it was built
docker images | grep kodex-sandbox
```

**If Docker is not available**, Kodex will use a local fallback (less secure, but functional for development).

## Step 7: Verify the Setup

```bash
# Run a quick check
python -c "
from kodex.config import get_settings
settings = get_settings()
print('✅ Settings loaded')
print(f'  Model: {settings.openai_model}')
print(f'  Qdrant: {settings.qdrant_url}')
print(f'  Sandbox: {settings.sandbox_image}')
"
```

---

## Usage

### Launch the UI (Recommended)

```bash
# Start the Streamlit Command Center
streamlit run kodex/ui/app.py

# Or via CLI
python -m kodex.main ui
```

The UI will open at [http://localhost:8501](http://localhost:8501).

### CLI Mode

```bash
# Index a repository
python -m kodex.main index /path/to/your/repo

# Run the healing agent (auto mode)
python -m kodex.main heal /path/to/your/repo --mode auto --index --report

# Run with human review
python -m kodex.main heal /path/to/your/repo --mode review --index
```

### CLI Options

```
usage: kodex heal [-h] [--mode {auto,review}] [--max-retries N]
                  [--index] [--report] [--log-level LEVEL]
                  repo

positional arguments:
  repo                  Path to the repository to heal

options:
  --mode {auto,review}  Agent mode (default: auto)
  --max-retries N       Max fix retries per error (default: 3)
  --index               Index the repository before healing
  --report              Generate an audit report after completion
  --log-level LEVEL     Logging level (default: INFO)
```

---

## Troubleshooting

### "Qdrant connection failed"

**Cause:** Qdrant Docker container is not running.

**Fix:**
```bash
docker-compose up -d qdrant
```

### "Sandbox image not found"

**Cause:** The kodex-sandbox Docker image hasn't been built.

**Fix:**
```bash
docker-compose build sandbox
```

### "OpenAI API key not set"

**Cause:** The `.env` file is missing or the API key is empty.

**Fix:**
1. Ensure `.env` exists in the project root
2. Set `OPENAI_API_KEY=sk-your-key-here`

### "Docker not available"

**Cause:** Docker Desktop is not installed or not running.

**Fix:**
1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/)
2. Start Docker Desktop
3. Wait for it to fully initialize

Kodex will still work without Docker (using local fallback), but the sandbox security features won't be active.

### "ModuleNotFoundError"

**Cause:** Dependencies not installed or virtual environment not activated.

**Fix:**
```bash
# Activate venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # macOS/Linux

# Reinstall
pip install -r requirements.txt
```

---

## Architecture Reference

```
Kodex/
├── kodex/
│   ├── agent/          # LangGraph orchestration
│   │   ├── state.py    # State schema
│   │   ├── nodes.py    # Node functions
│   │   └── graph.py    # Graph builder
│   ├── rag/            # RAG pipeline
│   │   ├── indexer.py  # Code indexer
│   │   ├── retriever.py # Multi-file retriever
│   │   └── engine.py   # LlamaIndex + Qdrant
│   ├── tools/          # Tool definitions
│   │   ├── registry.py # Dynamic tool registry
│   │   ├── lint_tool.py
│   │   ├── test_tool.py
│   │   ├── git_tool.py
│   │   ├── file_tool.py
│   │   └── sandbox_tool.py
│   ├── sandbox/        # Docker sandbox
│   │   └── docker_sandbox.py
│   ├── tracking/       # Observability
│   │   ├── token_tracker.py
│   │   ├── audit_logger.py
│   │   ├── session_store.py
│   │   └── report_generator.py
│   ├── ui/             # Streamlit UI
│   │   ├── app.py
│   │   ├── components/
│   │   └── styles/
│   ├── config.py       # Configuration
│   └── main.py         # CLI entry
├── tools_config.yaml   # Custom tools
├── .env.example        # Environment template
└── docker-compose.yml  # Docker services
```

---

*Built by Shivam Kolpyakwar • Kodex v1.0.0*
