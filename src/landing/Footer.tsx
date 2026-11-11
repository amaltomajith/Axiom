import { ArrowUpRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { LogoMark } from '@/components/Logo';
import { NAV_MENUS } from './data';
import { Globe } from './Globe';
import { GhostLink, StartLink } from './ui';

/** The closing panel: light pooling from the top-left corner, one last invitation. */
export function FinalCta() {
  return (
    <section id="start" aria-labelledby="start-title" className="px-4 py-16 sm:px-8 sm:py-24">
      <div className="lp-panel relative isolate mx-auto max-w-[1240px] overflow-hidden rounded-[28px] px-6 py-20 sm:px-16 sm:py-28">
        <div aria-hidden className="absolute -left-40 -top-40 -z-10 h-[520px] w-[520px] rounded-full bg-primary/35 blur-[130px]" />
        <div aria-hidden className="absolute -bottom-56 right-[10%] -z-10 h-[420px] w-[620px] rounded-full bg-primary/15 blur-[140px]" />
        <div aria-hidden className="absolute -right-24 top-1/2 -z-10 hidden aspect-square w-[620px] -translate-y-1/2 lg:block">
          <div className="lp-floor absolute inset-x-[12%] bottom-[8%] h-[18%]" />
          <Globe variant="cloud" points={26000} radius={0.3} tilt={0.25} speed={0.08} />
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

const COLUMNS = [
  { title: 'Product', links: NAV_MENUS[0].items },
  { title: 'Learn', links: NAV_MENUS[1].items },
];

/** Link cards, the name in big letters lit from behind, and the plain-words disclaimer. */
export function Footer() {
  return (
    <footer className="relative isolate overflow-hidden px-4 pt-16 sm:px-8">
      <div className="mx-auto max-w-[1240px]">
        <div className="grid gap-4 md:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_minmax(0,1fr)]">
          <div className="lp-card-lit flex flex-col rounded-[22px] p-6 sm:p-7">
            <Link to="/" aria-label="Axiom home" className="flex items-center gap-3 self-start rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-ring">
              <LogoMark className="h-8 w-8" />
              <span translate="no" className="lp-silver text-[0.95rem] font-semibold tracking-[0.34em]">
                AXIOM
              </span>
            </Link>
            <p className="mt-5 max-w-[34ch] text-body text-foreground/80">A patient trading partner that practices with paper money and tells you everything it does.</p>
            <StartLink size="sm" className="mt-8 self-start" />
          </div>
          {COLUMNS.map(col => (
            <nav key={col.title} aria-label={col.title} className="lp-card rounded-[22px] p-6 sm:p-7">
              <p className="text-caption font-medium uppercase tracking-[0.14em] text-primary">{col.title}</p>
              <ul className="mt-4 space-y-1">
                {col.links.map(l => (
                  <li key={l.href}>
                    <a
                      href={l.href}
                      {...(l.href.startsWith('http') ? { target: '_blank', rel: 'noreferrer' } : {})}
                      className="group flex items-center justify-between gap-3 rounded-lg py-1.5 text-body text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:text-foreground"
                    >
                      {l.title}
                      <ArrowUpRight aria-hidden className="h-4 w-4 opacity-0 transition-opacity group-hover:opacity-100" />
                    </a>
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>

        <div aria-hidden className="relative mt-14 select-none">
          <div className="absolute bottom-0 left-1/2 -z-10 h-[70%] w-[80%] -translate-x-1/2 rounded-full bg-primary/30 blur-[110px]" />
          <div className="absolute bottom-[-10%] left-1/2 -z-10 h-[30%] w-[40%] -translate-x-1/2 rounded-full bg-[hsl(199_95%_75%/0.5)] blur-[70px]" />
          <p translate="no" className="lp-wordmark pb-[0.04em] text-center text-[clamp(6rem,27vw,23rem)] font-semibold leading-[0.82] tracking-[-0.06em]">
            Axiom
          </p>
        </div>

        <div className="border-t border-white/[0.08] py-8 text-caption text-muted-foreground">
          <p className="max-w-[80ch]">Axiom trades with paper money only and is not financial advice. Results from practice runs do not predict future results.</p>
        </div>
      </div>
    </footer>
  );
}
