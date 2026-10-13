import { Link } from 'react-router-dom';
import { Logo } from '@/components/Logo';
import { Button } from '@/components/ui/button';
import { EVAL_REPORT, REPO } from './data';

export function FinalCta() {
  return (
    <section className="mx-auto max-w-[1200px] px-4 pb-24 sm:px-6 sm:pb-32">
      <div className="surface flex flex-col items-start justify-between gap-6 px-6 py-10 sm:px-10 md:flex-row md:items-center">
        <div className="max-w-[40ch]">
          <h2 className="text-h1">See a run for yourself</h2>
          <p className="mt-2 text-body text-muted-foreground">It works with no keys, on a local model, in about a minute.</p>
        </div>
        <Button asChild size="lg" className="shrink-0">
          <Link to="/app">Open terminal</Link>
        </Button>
      </div>
    </section>
  );
}

export function Footer() {
  return (
    <footer className="border-t border-border">
      <div className="mx-auto flex max-w-[1200px] flex-col gap-6 px-4 py-10 sm:px-6 md:flex-row md:items-center md:justify-between">
        <div>
          <Logo />
          <p className="mt-3 max-w-[48ch] text-caption text-muted-foreground">Research tooling, not financial advice. Daily bars and public filings only.</p>
        </div>
        <nav aria-label="Footer" className="flex flex-wrap gap-x-6 gap-y-2 text-small text-muted-foreground">
          <a className="hover:text-foreground" href="#how">How it works</a>
          <a className="hover:text-foreground" href="#mcp">MCP setup</a>
          <a className="hover:text-foreground" href={EVAL_REPORT} target="_blank" rel="noreferrer">Eval report</a>
          <a className="hover:text-foreground" href={REPO} target="_blank" rel="noreferrer">Source</a>
        </nav>
      </div>
    </footer>
  );
}
