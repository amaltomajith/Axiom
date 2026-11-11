import { Logo } from '@/components/Logo';
import { BACKTEST_DOC, NAV_LINKS, REPO } from './data';
import { Globe } from './Globe';
import { GhostLink, StartLink } from './ui';

/** The closing panel: light pooling from the top-left corner, one last invitation. */
export function FinalCta() {
  return (
    <section id="start" aria-labelledby="start-title" className="px-4 py-16 sm:px-8 sm:py-24">
      <div className="lp-panel relative isolate mx-auto max-w-[1240px] overflow-hidden rounded-[28px] px-6 py-20 sm:px-16 sm:py-28">
        <div aria-hidden className="absolute -left-40 -top-40 -z-10 h-[520px] w-[520px] rounded-full bg-primary/35 blur-[130px]" />
        <div aria-hidden className="absolute -bottom-56 right-[10%] -z-10 h-[420px] w-[620px] rounded-full bg-primary/15 blur-[140px]" />
        <div aria-hidden className="absolute -right-40 top-1/2 -z-10 hidden aspect-square w-[680px] -translate-y-1/2 lg:block">
          <Globe tilt={0.5} speed={0.04} count={8000} />
        </div>
        <h2 id="start-title" className="lp-silver max-w-[13ch] pb-2 text-[clamp(2.6rem,6vw,4.75rem)] font-semibold leading-[1.02] tracking-[-0.04em]">
          Practice first. Trust it later.
        </h2>
        <p className="mt-5 max-w-[44ch] text-body text-muted-foreground sm:text-[1.0625rem]">It is free, it never touches real money, and you can switch it off at any moment.</p>
        <div className="mt-9 flex flex-wrap gap-3">
          <StartLink />
          <GhostLink href="#how">See how it works</GhostLink>
        </div>
      </div>
    </section>
  );
}

export function Footer() {
  return (
    <footer className="relative isolate overflow-hidden px-4 pt-16 sm:px-8">
      <div className="mx-auto max-w-[1240px]">
        <div className="grid gap-10 md:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1fr)]">
          <div>
            <Logo />
            <p className="mt-4 max-w-[34ch] text-small text-muted-foreground">A patient trading partner that practices with paper money and tells you everything it does.</p>
          </div>
          <nav aria-label="Product">
            <p className="text-small font-medium text-primary">Product</p>
            <ul className="mt-4 space-y-3 text-small text-muted-foreground">
              {NAV_LINKS.map(l => (
                <li key={l.href}>
                  <a href={l.href} className="hover:text-foreground">
                    {l.label}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
          <nav aria-label="Project">
            <p className="text-small font-medium text-primary">Project</p>
            <ul className="mt-4 space-y-3 text-small text-muted-foreground">
              <li>
                <a href={REPO} target="_blank" rel="noreferrer" className="hover:text-foreground">
                  Source code
                </a>
              </li>
              <li>
                <a href={BACKTEST_DOC} target="_blank" rel="noreferrer" className="hover:text-foreground">
                  Practice report
                </a>
              </li>
            </ul>
          </nav>
        </div>

        <div aria-hidden className="relative mt-16 select-none">
          <div className="absolute left-1/2 top-1/2 -z-10 h-48 w-[70%] -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary/25 blur-[90px]" />
          <p className="bg-gradient-to-b from-white/35 to-white/[0.03] bg-clip-text text-center text-[clamp(6rem,26vw,22rem)] font-semibold leading-[0.8] tracking-[-0.06em] text-transparent">Axiom</p>
        </div>

        <div className="mt-10 border-t border-white/[0.07] py-8 text-caption text-muted-foreground">
          <p className="max-w-[80ch]">Axiom trades with paper money only and is not financial advice. Results from practice runs do not predict future results.</p>
        </div>
      </div>
    </footer>
  );
}
