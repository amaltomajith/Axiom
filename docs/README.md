# Docs index

Every document in the repo, what it covers, and whether it still describes the code. The same list is on the
live hub page ([axiom-ten-henna.vercel.app/hub](https://axiom-ten-henna.vercel.app/hub)); `src/test/hub.test.tsx`
fails if the two drift apart or a path stops existing.

**Status:** *current* means kept in step with the code. *Generated* means written by a script; don't edit it by
hand. *Historical* means it records a decision or plan from the past and is kept for context only.

## Start here

| Doc | What it covers | Status |
|---|---|---|
| [README](../README.md) | The parts, live links, one-command quick start, design claims and limits | current |
| [Backend](../backend/README.md) | Every Python entry point, HTTP route and setting | current |
| [Axiom Watch](../angular/README.md) | Run, test, containerise and deploy the Angular app | current |

## How it works

| Doc | What it covers | Status |
|---|---|---|
| [Architecture](architecture.md) | Agents, guardrails, the security model and how evals work | current |
| [MCP clients](mcp-clients.md) | Add the 11 research tools to Claude Desktop or Claude Code | current |
| [RxJS and NgRx notes](../angular/LEARNING.md) | Why each operator in Axiom Watch was chosen, with interview questions | current |

## Running it in production

| Doc | What it covers | Status |
|---|---|---|
| [Deployment](deployment.md) | Vercel and Neon step by step, the env var table, Cloud Run as the fallback | current |

## Data platform

| Doc | What it covers | Status |
|---|---|---|
| [Data platform design](gcp-architecture.md) | BigQuery layers, data quality, scheduling, what billing would change | current |
| [Data governance](gcp-governance.md) | IAM, Workload Identity Federation, PII handling and secrets | current |
| [Data platform results](../RESULTS.md) | Measured numbers and a dated log of each phase. Counts there are as of each phase | current |

## Evidence and write-ups

| Doc | What it covers | Status |
|---|---|---|
| [Eval report](eval-report.md) | Latest honesty and prompt-injection results. Written by `backend/scripts/capture_snapshot.py` | generated |
| [Project summary](PROJECT-SUMMARY.md) | Portfolio write-up and resume bullets | current |

## Historical

| Doc | What it covers | Status |
|---|---|---|
| [Axiom Watch plan](../angular/PLAN.md) | The endpoints, state shape and build order agreed before Axiom Watch was built | historical |
| [Original blueprint](../refs/axiom_agentic_architecture_blueprint.md) | The design before the rebuild. Supabase and the mock models it describes are gone | historical |
| [Hosting research](../reports/Free%20hosting%20for%20Axiom%20backend.md) | Free hosting options compared. Vercel was chosen instead of the Cloudflare setup it recommends | historical |
