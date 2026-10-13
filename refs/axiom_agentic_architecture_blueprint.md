# Axiom: Agentic Refactor Blueprint

## 🎯 Project Objective
Transform "Axiom", currently a frontend-heavy stock dashboard with mocked machine learning models, into an **Autonomous Market Intelligence & Portfolio Analyst Terminal**. 

This project must serve as an enterprise-grade portfolio piece demonstrating deep expertise in **Agentic AI, Model Context Protocol (MCP), Multi-Agent Orchestration, and Composio tool integrations.**

## 🛑 Current State vs. Target State
* **Current State:** 
  * React 18 / Vite / shadcn frontend.
  * Fake predictive models (`predictLSTM`, `predictProphet`, `predictXGBoost` in `src/lib/models.ts` are just random walks).
  * Mock indicators and unverified paper trading.
  * Security risks (committed `.env` and open Supabase edge functions).
* **Target State:**
  * **Frontend:** Streaming Markdown UI with a real-time "Agent Reasoning Trace" drawer showing LLM thoughts and tool calls.
  * **Data Layer (Read):** Custom **MCP Server** that exposes financial APIs (Twelve Data, Finnhub, SEC filings) as standardized tools to the agent.
  * **Action Layer (Write):** **Composio** integration for external tool execution (Notion, Google Sheets, Slack).
  * **Brain:** Multi-Agent workflow orchestrating technical, fundamental, and risk analysis.

---

## 🏗️ Target Architecture Overview

```text
┌────────────────────────────────────────────────────────┐
│                   Axiom Terminal (UI)                  │
│       React 18 / Tailwind / Streaming SSE / Logs       │
└───────────────────────────▲────────────────────────────┘
                            │ SSE / WebSocket Stream
┌───────────────────────────┴────────────────────────────┐
│         Autonomous Financial Research Agent            │
│         (Multi-Agent Orchestration Engine)             │
│   • Technical Analyst        • Fundamental Auditor     │
│   • Risk/Sizing Guard        • Lead Synthesizer        │
└──────────────┬─────────────────────────────┬───────────┘
               │                             │
    ┌──────────▼──────────┐       ┌──────────▼──────────┐
    │  MCP Server (Read)  │       │ Composio (Write)    │
    │  • Market APIs      │       │ • Notion (Reports)  │
    │  • SEC Filings      │       │ • Sheets (Trades)   │
    │  • Local Indicators │       │ • Slack (Alerts)    │
    └─────────────────────┘       └─────────────────────┘
```

---

## 📋 Execution Phases for the Coding Agent

### Phase 1: Codebase Hygiene & Cleanup
* **Goal:** Remove technical debt and fake implementations.
* **Tasks:**
  1. Remove `.env` from tracking and establish a proper `.env.example`.
  2. Delete the mock ML models in `src/lib/models.ts` (Prophet, XGBoost, LSTM).
  3. Clean up unused lockfiles (keep only one, e.g., `package-lock.json` or `bun.lockb`).
  4. Fix existing ESLint `any` types and empty interface errors in the shadcn components.
  5. Rewrite `src/lib/indicators.ts` to use real mathematical formulas (e.g., Wilder's smoothing for RSI, standard MACD).

### Phase 2: Implement the MCP Server Layer (Context & Read)
* **Goal:** Standardize how the LLM accesses financial data.
* **Tasks:**
  1. Create a local MCP server (Python or TypeScript) that connects to Twelve Data and Finnhub.
  2. Expose specific tools:
     * `get_historical_ohlcv(ticker, timeframe)`
     * `get_company_news_sentiment(ticker)`
     * `fetch_sec_10k_summary(ticker)`
  3. Ensure the AI agent can call these tools dynamically rather than relying on frontend polling.

### Phase 3: Multi-Agent Orchestration Workflow
* **Goal:** Replace the "ensemble model vote" with a chain of reasoning.
* **Tasks:**
  1. Implement an orchestration loop (using LangChain, LlamaIndex, or a custom loop).
  2. **Technical Agent:** Analyzes MCP price data and indicator data.
  3. **Fundamental Agent:** Analyzes MCP news and SEC data.
  4. **Synthesizer Agent:** Debates the findings and outputs a structured Markdown investment memo.

### Phase 4: Composio Integration (Action Space)
* **Goal:** Give the agent the ability to execute real-world tasks.
* **Tasks:**
  1. Integrate the Composio SDK.
  2. Create an action workflow: When the Synthesizer Agent finalizes a "Strong Buy/Sell" thesis, trigger a Composio action to:
     * Draft and format a Notion page with the full report.
     * Log the simulated trade execution into a Google Sheet.
     * Send a summary alert to a designated Slack/Discord channel.

### Phase 5: UI & Streaming (The "Showcase" Factor)
* **Goal:** Make the agentic process visible to the user.
* **Tasks:**
  1. Update `Index.tsx` to handle Server-Sent Events (SSE).
  2. Build an "Agent Trace" component (a terminal-like sliding drawer) that streams the agent's internal monologue:
     * *Example:* `[System] Invoking MCP Tool: get_historical_ohlcv(AAPL)`
     * *Example:* `[Fundamental Agent] Reading latest 10-Q risk factors...`
  3. Render the final Synthesizer report in beautifully formatted Markdown in the main UI panel.