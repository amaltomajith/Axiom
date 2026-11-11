#!/usr/bin/env node
/**
 * One command for local development: the API (with the trader) and the React terminal together.
 *
 *   npm run dev:all
 *   npm run dev:all -- --only api,terminal
 *   npm run dev:all -- --prod-db      (let the local API use DATABASE_URL from backend/.env)
 *
 * Plain Node, no dependencies. Each process gets a coloured prefix; Ctrl+C stops all of them.
 */
import { spawn, spawnSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { connect } from 'node:net';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const WIN = process.platform === 'win32';

const PARTS = {
  api: { label: 'api', color: 36, cwd: 'backend', cmd: 'uv run python -m axiom.api', port: 8000, url: 'http://localhost:8000/api/status' },
  terminal: { label: 'terminal', color: 35, cwd: '.', cmd: 'npm run dev', port: 5173, url: 'http://localhost:5173/app' },
};

const HELP = `Start Axiom locally.

  npm run dev:all [-- options]

Options
  --only <list>   Comma-separated parts to start: ${Object.keys(PARTS).join(', ')} (default: all)
  --prod-db       Let the local API use DATABASE_URL from backend/.env. Off by default, because that file
                  usually comes from "vercel env pull" and points at the production database.
  --help          Show this text.

Notes
  * The API needs uv. If "uv sync" fails on the F: drive venv, set UV_PROJECT_ENVIRONMENT to a venv
    elsewhere (for example C:/Users/<you>/.venvs/axiom) before running this.
  * Analysis needs an LLM: a free key in backend/.env, or Ollama running with qwen3:8b.`;

// ---------------------------------------------------------------- arguments
const args = process.argv.slice(2);
if (args.includes('--help') || args.includes('-h')) {
  console.log(HELP);
  process.exit(0);
}
const onlyArg = args.includes('--only') ? args[args.indexOf('--only') + 1] : undefined;
const wanted = onlyArg ? onlyArg.split(',').map(s => s.trim()).filter(Boolean) : Object.keys(PARTS);
const unknown = wanted.filter(w => !(w in PARTS));
if (unknown.length) {
  console.error(`Unknown part: ${unknown.join(', ')}. Choose from ${Object.keys(PARTS).join(', ')}.`);
  process.exit(2);
}
const prodDb = args.includes('--prod-db');

// ---------------------------------------------------------------- helpers
const paint = (code, s) => (process.stdout.isTTY ? `\x1b[${code}m${s}\x1b[0m` : s);
const note = s => console.log(`${paint('2', 'dev')}  ${s}`);
const warn = s => console.log(`${paint('33', 'dev')}  ${s}`);

function readDotenv(path) {
  if (!existsSync(path)) return {};
  const out = {};
  for (const line of readFileSync(path, 'utf-8').split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/);
    if (m) out[m[1]] = m[2].replace(/^["']|["']$/g, '');
  }
  return out;
}

function portBusy(port) {
  return new Promise(res => {
    const sock = connect({ port, host: '127.0.0.1' });
    sock.once('connect', () => (sock.destroy(), res(true)));
    sock.once('error', () => res(false));
    sock.setTimeout(400, () => (sock.destroy(), res(false)));
  });
}

async function ollamaUp() {
  try {
    const ctrl = AbortSignal.timeout(800);
    return (await fetch('http://localhost:11434/api/tags', { signal: ctrl })).ok;
  } catch {
    return false;
  }
}

const has = cmd => spawnSync(WIN ? 'where' : 'which', [cmd], { stdio: 'ignore' }).status === 0;

// ---------------------------------------------------------------- preflight
const plan = [];
const env = { ...process.env, FORCE_COLOR: '1' };

if (wanted.includes('api')) {
  if (!has('uv')) {
    warn('Skipping api: uv is not on PATH. Install it from https://docs.astral.sh/uv/ and rerun.');
  } else {
    const dotenv = readDotenv(join(ROOT, 'backend', '.env'));
    const apiEnv = { ...env };
    if (dotenv.DATABASE_URL && !prodDb && process.env.DATABASE_URL === undefined) {
      apiEnv.DATABASE_URL = '';
      note('backend/.env sets DATABASE_URL (normally production). The local API uses SQLite instead; pass --prod-db to override.');
    } else if (dotenv.DATABASE_URL && prodDb) {
      warn('--prod-db: the local API is writing to the database in backend/.env. Runs, theses and approvals land there.');
    }
    if (process.env.CORS_ORIGINS === undefined) apiEnv.CORS_ORIGINS = 'http://localhost:5173';
    if (dotenv.AXIOM_API_TOKEN) note('backend/.env sets AXIOM_API_TOKEN: paste it with the key icon in the terminal to unlock writes.');
    if (!dotenv.GROQ_API_KEY && !dotenv.GEMINI_API_KEY && !dotenv.OPENROUTER_API_KEY && !dotenv.CEREBRAS_API_KEY && !(await ollamaUp())) {
      warn('No LLM key in backend/.env and Ollama is not answering on :11434. Charts work, analysis will fail.');
    }
    plan.push({ ...PARTS.api, env: apiEnv });
  }
}

if (wanted.includes('terminal')) {
  if (!existsSync(join(ROOT, 'node_modules'))) warn('No node_modules at the repo root: run "npm install" first.');
  plan.push({ ...PARTS.terminal, env: { ...env, VITE_API_BASE_URL: process.env.VITE_API_BASE_URL ?? 'http://localhost:8000' } });
}

const runnable = [];
for (const p of plan) {
  if (await portBusy(p.port)) warn(`Skipping ${p.label}: port ${p.port} is already in use (already running?).`);
  else runnable.push(p);
}
if (!runnable.length) {
  warn('Nothing to start.');
  process.exit(1);
}

// ---------------------------------------------------------------- run
const width = Math.max(...runnable.map(p => p.label.length));
const children = [];
let stopping = false;

function pipe(stream, prefix) {
  let buf = '';
  stream.on('data', chunk => {
    buf += chunk.toString();
    const lines = buf.split(/\r?\n/);
    buf = lines.pop() ?? '';
    for (const line of lines) if (line.trim()) process.stdout.write(`${prefix} ${line}\n`);
  });
  stream.on('end', () => buf.trim() && process.stdout.write(`${prefix} ${buf}\n`));
}

for (const p of runnable) {
  const prefix = paint(p.color, p.label.padEnd(width));
  const child = spawn(p.cmd, { cwd: join(ROOT, p.cwd), env: p.env, shell: true, windowsHide: true });
  children.push(child);
  pipe(child.stdout, prefix);
  pipe(child.stderr, prefix);
  child.on('exit', code => {
    if (!stopping) warn(`${p.label} exited${code === null ? '' : ` with code ${code}`}.`);
    if (children.every(c => c.exitCode !== null || c.signalCode !== null)) process.exit(0);
  });
}

console.log('');
for (const p of runnable) note(`${paint(p.color, p.label.padEnd(width))}  ${p.url}`);
note('Ctrl+C stops everything.\n');

function stop() {
  if (stopping) return;
  stopping = true;
  note('Stopping...');
  for (const c of children) {
    if (c.exitCode !== null || !c.pid) continue;
    // A shell child on Windows does not pass signals on: kill the whole tree.
    if (WIN) spawnSync('taskkill', ['/pid', String(c.pid), '/T', '/F'], { stdio: 'ignore' });
    else c.kill('SIGINT');
  }
  setTimeout(() => process.exit(0), 3000).unref();
}
process.on('SIGINT', stop);
process.on('SIGTERM', stop);
