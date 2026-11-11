/**
 * The one list of what Axiom is made of. The hub page renders it, and tests check it against the repo
 * (every docs path exists, every live URL is in the README), so the map cannot quietly drift.
 */
import { REPO } from '@/landing/data';

export const LIVE = {
  terminal: 'https://axiom-ten-henna.vercel.app',
  api: 'https://axiom-api-three.vercel.app',
  watch: 'https://axiom-watch.vercel.app',
} as const;

export const GITHUB_API = 'https://api.github.com/repos/amaltomajith/Axiom';

export type PartId = 'api' | 'terminal' | 'watch' | 'mcp' | 'data';

export interface Part {
  id: PartId;
  name: string;
  /** One sentence: what a person gets from it. */
  purpose: string;
  /** Where it is deployed, or null when it only runs on your machine. */
  live: string | null;
  liveLabel: string;
  /** Repo folder that holds it. */
  folder: string;
  /** The command that starts just this part, from the repo root. */
  run: string;
  port: number | null;
  stack: string;
  needs: string;
  /** Repo-relative docs path, linked on GitHub. */
  docs: string;
}

export const PARTS: Part[] = [
  {
    id: 'terminal',
    name: 'Axiom terminal',
    purpose: 'The main app. Run the agent pipeline on a ticker and read the cited memo, plus backtests, paper trades, the scorecard and approvals.',
    live: LIVE.terminal,
    liveLabel: 'axiom-ten-henna.vercel.app',
    folder: 'src/',
    run: 'npm run dev',
    port: 5173,
    stack: 'React 18, Vite, Tailwind, TanStack Query',
    needs: 'Node 20 or newer',
    docs: 'README.md',
  },
  {
    id: 'watch',
    name: 'Axiom Watch',
    purpose: 'A lighter watchlist app. Search tickers, keep a personal list without signing in and watch a run step by step.',
    live: LIVE.watch,
    liveLabel: 'axiom-watch.vercel.app',
    folder: 'angular/',
    run: 'cd angular && npm start',
    port: 4200,
    stack: 'Angular 22, RxJS, NgRx',
    needs: 'Node 24, or 22.22.3 and newer',
    docs: 'angular/README.md',
  },
  {
    id: 'api',
    name: 'Axiom API',
    purpose: 'The backend both apps talk to: the multi-agent pipeline, guardrails, memory, approvals and the weekday cron.',
    live: LIVE.api,
    liveLabel: 'axiom-api-three.vercel.app',
    folder: 'backend/axiom/',
    run: 'cd backend && uv run python -m axiom.api',
    port: 8000,
    stack: 'Python 3.12, FastAPI, SSE, Postgres or SQLite',
    needs: 'uv. A free LLM key or Ollama for analysis',
    docs: 'backend/README.md',
  },
  {
    id: 'mcp',
    name: 'MCP server',
    purpose: 'The same 11 research tools the agents use, served over MCP so Claude Desktop or Claude Code can call them.',
    live: null,
    liveLabel: 'Runs on your machine',
    folder: 'backend/axiom/mcp_server/',
    run: 'cd backend && uv run python -m axiom.mcp_server',
    port: null,
    stack: 'FastMCP, stdio or streamable HTTP',
    needs: 'uv. No keys',
    docs: 'docs/mcp-clients.md',
  },
  {
    id: 'data',
    name: 'Data platform',
    purpose: 'Copies every run from the app into BigQuery each weekday, checks data quality and builds marts. Also a PySpark benchmark and a model study.',
    live: `${REPO}/actions/workflows/data-platform.yml`,
    liveLabel: 'GitHub Actions, weekdays 14:00 UTC',
    folder: 'backend/data_platform/',
    run: 'cd backend && uv run python -m data_platform run --env dev',
    port: null,
    stack: 'BigQuery sandbox, SQL, PySpark in Docker',
    needs: 'A GCP project and gcloud sign-in',
    docs: 'docs/gcp-architecture.md',
  },
];

export type DocStatus = 'current' | 'generated' | 'historical';

export interface Doc {
  path: string;
  title: string;
  purpose: string;
  status: DocStatus;
}

/** Mirrors docs/README.md. A test fails if a path here is missing from the repo or from that index. */
export const DOCS: Doc[] = [
  { path: 'README.md', title: 'README', purpose: 'Start here: the parts, quick start and limits', status: 'current' },
  { path: 'docs/README.md', title: 'Docs index', purpose: 'Every doc, what it covers and whether it is current', status: 'current' },
  { path: 'backend/README.md', title: 'Backend', purpose: 'Every command, route and setting in the Python side', status: 'current' },
  { path: 'docs/architecture.md', title: 'Architecture', purpose: 'Agents, guardrails, security model and evals', status: 'current' },
  { path: 'docs/deployment.md', title: 'Deployment', purpose: 'Vercel, Neon and env vars, with Cloud Run as the fallback', status: 'current' },
  { path: 'docs/mcp-clients.md', title: 'MCP clients', purpose: 'Use the tools from Claude Desktop or Claude Code', status: 'current' },
  { path: 'angular/README.md', title: 'Axiom Watch', purpose: 'Run, test, containerise and deploy the Angular app', status: 'current' },
  { path: 'docs/gcp-architecture.md', title: 'Data platform design', purpose: 'The BigQuery ELT, data quality and what billing would change', status: 'current' },
  { path: 'docs/gcp-governance.md', title: 'Data governance', purpose: 'IAM, Workload Identity Federation, PII and secrets', status: 'current' },
  { path: 'RESULTS.md', title: 'Data platform results', purpose: 'Measured numbers and the log of each phase', status: 'current' },
  { path: 'docs/eval-report.md', title: 'Eval report', purpose: 'Latest honesty and prompt injection results', status: 'generated' },
  { path: 'docs/PROJECT-SUMMARY.md', title: 'Project summary', purpose: 'Portfolio write up and resume bullets', status: 'current' },
  { path: 'angular/LEARNING.md', title: 'RxJS and NgRx notes', purpose: 'What Axiom Watch teaches, with interview questions', status: 'current' },
  { path: 'angular/PLAN.md', title: 'Axiom Watch plan', purpose: 'Endpoints, state shape and the build order', status: 'historical' },
  { path: 'refs/axiom_agentic_architecture_blueprint.md', title: 'Original blueprint', purpose: 'The design before the rebuild. Supabase and mock models are gone', status: 'historical' },
  { path: 'reports/Free hosting for Axiom backend.md', title: 'Hosting research', purpose: 'Free hosting options compared before Vercel was chosen', status: 'historical' },
];

export const blobUrl = (path: string) => `${REPO}/blob/main/${path.split('/').map(encodeURIComponent).join('/')}`;

export const LAUNCHER = `npm run dev:all              # API, terminal and Axiom Watch together
npm run dev:all -- --only api,terminal
npm run dev:all -- --help`;
