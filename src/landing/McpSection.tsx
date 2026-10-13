import { CodeBlock } from './CodeBlock';
import { MCP_TOOLS } from './data';

const CLAUDE_CODE = 'claude mcp add axiom -- uv --directory /path/to/Axiom/backend run python -m axiom.mcp_server';

const DESKTOP = `{
  "mcpServers": {
    "axiom": {
      "command": "uv",
      "args": ["--directory", "/path/to/Axiom/backend", "run", "python", "-m", "axiom.mcp_server"]
    }
  }
}`;

/** The one horizontal scroller on the page: eleven tool names, snapping into place. */
export function McpSection() {
  return (
    <section id="mcp" className="mx-auto max-w-[1200px] px-4 pb-24 sm:px-6 sm:pb-32">
      <div className="max-w-[60ch]">
        <h2 className="text-h1">Use it from Claude Desktop</h2>
        <p className="mt-3 text-body text-muted-foreground">The tools the agents use are a standard MCP server. Add it once, then ask in plain language.</p>
      </div>

      <div className="-mx-4 mt-10 overflow-x-auto px-4 pb-2 [scrollbar-width:none] sm:-mx-6 sm:px-6" tabIndex={0} aria-label="Available tools, scroll sideways">
        <ul className="flex snap-x snap-mandatory gap-2.5">
          {MCP_TOOLS.map(t => (
            <li key={t} className="snap-start">
              <span className="inline-flex h-10 items-center whitespace-nowrap rounded-full border border-border bg-card px-4 font-mono text-caption">{t}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="mt-8 grid gap-6 md:grid-cols-2">
        <div className="min-w-0">
          <h3 className="mb-2 text-small font-semibold">Claude Code</h3>
          <CodeBlock code={CLAUDE_CODE} label="Claude Code command" />
        </div>
        <div className="min-w-0">
          <h3 className="mb-2 text-small font-semibold">Claude Desktop</h3>
          <CodeBlock code={DESKTOP} label="Claude Desktop configuration" />
        </div>
      </div>
      <p className="mt-5 max-w-[65ch] text-small text-muted-foreground">Every result carries its source, provider and as-of date, and backtests return a verdict the assistant is told not to overstate.</p>
    </section>
  );
}
