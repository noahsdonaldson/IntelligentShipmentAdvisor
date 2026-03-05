# Intelligent Shipment Risk Advisor
### API-Only vs. MCP + ReAct — A Study in Agent Architecture

---

## Core Hypothesis

> **Strict, pre-defined API call chains work fine for linear agent workflows, but break down under dynamic, multi-hop reasoning. MCP + ReAct agents solve this by letting the model decide what to call and when — enabling adaptive workflows that APIs alone cannot support.**

---

## The Scenario

A customer service agent must answer: **"Is my package going to arrive on time?"**

This sounds simple but requires:
1. Looking up the customer account
2. Finding their active shipment(s) — there could be one or many
3. Getting weather at origin **and** destination city
4. Checking carrier status for delay flags
5. Synthesising a risk assessment with natural-language reasoning

The edge case that breaks rigid APIs: **one account has two shipments to different cities, one carrier is disrupted, and weather at one destination is high-risk.**

---

## Project Structure

```
IntelligentShipmentAdvisor/
│
├── infrastructure/
│   ├── logistics_api.py            # Mock FastAPI: accounts, shipments, carriers
│   ├── weather_api.py              # Mock FastAPI: weather by city
│   ├── logistics_mcp_server.py     # MCP server — internal logistics domain
│   └── weather_mcp_server.py       # MCP server — third-party weather provider
│
├── notebooks/
│   ├── 01_api_strict_workflow.ipynb    # Hard-coded API chain — happy path then failure
│   ├── 02_mcp_react_workflow.ipynb     # ReAct agent connecting to BOTH MCP servers
│   └── 03_analysis_and_blog_prep.ipynb # Side-by-side comparison, charts, blog prep
│
├── requirements.txt
└── README.md
```

### Why Two MCP Servers?

In production you never own the weather data. A commercial provider  
(Tomorrow.io, The Weather Company, etc.) would publish their own MCP server.  
Your internal logistics server and their weather server are two independent  
MCP endpoints. The ReAct agent connects to both, receives a **unified tool  
catalogue**, and reasons across them without any bespoke integration glue.

```
┌──────────────────────────────────────────────────────────────┐
│                    ReAct Agent (LLM client)                   │
│                                                              │
│  Connects to ──► logistics_mcp_server   (tools: 4)  ← yours │
│  Connects to ──► weather_mcp_server     (tools: 2)  ← theirs│
│                                                              │
│  Unified tool catalogue seen by model:  6 tools total        │
│  Model doesn't know or care which server owns which tool.    │
└──────────────────────────────────────────────────────────────┘
```

This is the USB-C analogy made concrete: write your server once,  
plug into any MCP-compatible LLM client.

---

## Build Plan

### Phase 0 — Environment Setup
```bash
cd IntelligentShipmentAdvisor
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # add your OPENAI_API_KEY or ANTHROPIC_API_KEY

# Register the venv as a named Jupyter kernel (run once)
python -m ipykernel install --user --name=IntelligentShipmentAdvisor --display-name "Intelligent Shipment Advisor"
```

> After running the command above, open JupyterLab and select **"Intelligent Shipment Advisor"** from the kernel picker in each notebook.

### Phase 1 — Infrastructure (Mock Servers)

| File | Responsibility |
|------|---------------|
| `infrastructure/logistics_api.py` | FastAPI serving accounts, shipments, carrier status |
| `infrastructure/weather_api.py` | FastAPI serving weather by city with risk levels |
| `infrastructure/mcp_server.py` | MCP server wrapping all tools, annotated as tutorial |

**Start servers:**
```bash
# Terminal 1 — Logistics REST API
uvicorn infrastructure.logistics_api:app --port 8001 --reload

# Terminal 2 — Weather REST API
uvicorn infrastructure.weather_api:app --port 8002 --reload

# Terminal 3 — Internal Logistics MCP Server (your system)
python infrastructure/logistics_mcp_server.py

# Terminal 4 — Third-Party Weather MCP Server (provider's system)
python infrastructure/weather_mcp_server.py
```

### Phase 2 — Notebooks (in order)

| Notebook | Purpose |
|----------|---------|
| `01_api_strict_workflow.ipynb` | Build + break the rigid API chain |
| `02_mcp_react_workflow.ipynb` | ReAct agent solving the same edge case |
| `03_analysis_and_blog_prep.ipynb` | Comparison table, latency chart, blog material |

---

## Mock Data — Edge Cases

### Accounts
| ID | Name | Tier | Home City |
|----|------|------|-----------|
| `ACC-001` | Alice Chen | Gold | Chicago |
| `ACC-002` | Bob Martinez | Standard | New York | ← **two shipments**|
| `ACC-003` | Carol White | Platinum | Seattle |

### Shipments for ACC-002 (the edge case account)
| ID | Origin | Destination | Carrier | ETA |
|----|--------|-------------|---------|-----|
| `SHP-101` | New York | Miami | `CARR-A` | +2 days |
| `SHP-102` | New York | Denver | `CARR-B` | +3 days | ← carrier disrupted |

### Carrier Status
| ID | Status | Note |
|----|--------|------|
| `CARR-A` | `on_time` | No issues |
| `CARR-B` | `disrupted` | Major hub delay — Denver region |

### Weather Risk
| City | Condition | Risk Level |
|------|-----------|-----------|
| Denver | Blizzard | `high` |
| Miami | Sunny | `low` |
| New York | Cloudy | `low` |
| Chicago | Rain | `medium` |
| Seattle | Storm | `high` |

---

## Key Architectural Trade-offs

| Dimension | API-Only Agent | MCP + ReAct Agent |
|-----------|---------------|-------------------|
| Workflow control | Developer | Model |
| Handles dynamic data | No — requires re-engineering | Yes — discovers and adapts |
| Debuggability | High — deterministic | Medium — trace-based |
| Latency | Lower | Higher (multi-hop reasoning) |
| Token cost | Lower | Higher |
| Correctness on edge cases | Fails silently | Handles gracefully |
| Right tool for... | ETL, integrations, pipelines | Assistants, open-ended queries |

---

## Tech Stack

| Layer | Library |
|-------|---------|
| Mock APIs | FastAPI + Uvicorn |
| MCP Server | `mcp` Python SDK |
| Agent Orchestration | LangChain ReAct + custom loop |
| LLM Backend | OpenAI GPT-4o or Anthropic Claude (configurable) |
| Notebooks | Jupyter + ipywidgets |
| Visualisation | matplotlib, networkx, rich |

---

## Environment Variables

```env
# .env
LLM_PROVIDER=openai          # or: anthropic
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
LOGISTICS_API_URL=http://localhost:8001
WEATHER_API_URL=http://localhost:8002
```

---

## Hypothesis Verdict (Spoiler)

The study confirms the hypothesis. For the happy path (single shipment, no disruptions) the rigid API chain is **faster, cheaper, and simpler**. For the edge case — two shipments, disrupted carrier, high-risk weather — the API chain silently returns partial results or crashes. The MCP + ReAct agent handles it gracefully, backtracks appropriately, and produces a coherent natural-language risk summary. The right architecture depends entirely on whether your workflow is closed or open-ended.
