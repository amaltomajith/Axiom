import { ArrowDown, ArrowRight } from 'lucide-react';
import { Fragment } from 'react';

const CHAIN = [
  { name: 'Groq', note: 'free tier' },
  { name: 'Gemini', note: 'free tier' },
  { name: 'OpenRouter', note: 'free models' },
  { name: 'Ollama', note: 'on your machine' },
];

const LIMITS = [
  'Prices are daily bars, not real time.',
  'News sentiment is a keyword baseline, so the headlines are shown too.',
  'The number check proves a figure exists in the cited result, not that it means what the claim says.',
  'Small free models need guardrails, and the eval report counts how often they were used.',
  'The Notion, Sheets and Slack path is built to the SDK but has not been run against a live account.',
  'Backtesting a few simple rules on one stock proves very little, and Axiom says so.',
];

export function StackSection() {
  return (
    <section className="mx-auto max-w-[1200px] px-4 pb-24 sm:px-6 sm:pb-32">
      <div className="max-w-[60ch]">
        <h2 className="text-h1">Free to run, honest about limits</h2>
        <p className="mt-3 text-body text-muted-foreground">Rate limits move the work to the next provider. With no keys at all it runs on a local model.</p>
      </div>

      <ol className="mt-10 flex flex-col items-stretch gap-2 md:flex-row md:items-center" aria-label="Model fallback order">
        {CHAIN.map((c, i) => (
          <Fragment key={c.name}>
            <li className="surface-quiet flex flex-1 items-baseline justify-between gap-3 px-5 py-4 md:flex-col md:items-start md:gap-0.5">
              <span className="text-h3">{c.name}</span>
              <span className="text-caption text-muted-foreground">{c.note}</span>
            </li>
            {i < CHAIN.length - 1 && (
              <li aria-hidden className="flex justify-center text-muted-foreground">
                <ArrowRight className="hidden h-4 w-4 md:block" />
                <ArrowDown className="h-4 w-4 md:hidden" />
              </li>
            )}
          </Fragment>
        ))}
      </ol>

      <h3 className="mb-4 mt-14 text-h3">What it does not do</h3>
      <ul className="grid gap-x-12 gap-y-3 md:grid-cols-2">
        {LIMITS.map(l => (
          <li key={l} className="relative max-w-[52ch] pl-4 text-small text-muted-foreground before:absolute before:left-0 before:top-[0.55em] before:h-1 before:w-1 before:rounded-full before:bg-muted-foreground/50">
            {l}
          </li>
        ))}
      </ul>
    </section>
  );
}
