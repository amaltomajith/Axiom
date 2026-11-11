import { AnimatePresence, motion } from 'motion/react';
import { ChevronDown, Github, History, LayoutGrid, Menu, MessageCircleQuestion, ShieldCheck, SlidersHorizontal, Sparkles, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { LogoMark } from '@/components/Logo';
import { spring, useReducedMotion } from '@/lib/motion';
import { cn } from '@/lib/utils';
import { NAV_MENUS, REPO } from './data';
import { StartLink } from './ui';

const ICONS: Record<string, typeof Sparkles> = {
  '#how': Sparkles,
  '#modes': SlidersHorizontal,
  '#safety': ShieldCheck,
  '#gateway': LayoutGrid,
  '#faq': MessageCircleQuestion,
};
const iconFor = (href: string) => ICONS[href] ?? (href === REPO ? Github : History);
const external = (href: string) => (href.startsWith('http') ? { target: '_blank', rel: 'noreferrer' } : {});

type Item = { href: string; title: string; note: string };

function MenuItem({ item, onPick }: { item: Item; onPick: () => void }) {
  const Icon = iconFor(item.href);
  return (
    <a
      href={item.href}
      {...external(item.href)}
      onClick={onPick}
      className="group/item flex items-start gap-3.5 rounded-xl p-3 outline-none transition-colors hover:bg-white/[0.05] focus-visible:bg-white/[0.06]"
    >
      <span className="lp-icon flex h-10 w-10 shrink-0 items-center justify-center rounded-[10px]">
        <Icon aria-hidden className="h-[18px] w-[18px] text-primary" strokeWidth={1.75} />
      </span>
      <span className="min-w-0">
        <span className="block text-body font-medium text-foreground">{item.title}</span>
        <span className="mt-0.5 block text-caption text-muted-foreground transition-colors group-hover/item:text-foreground/75">{item.note}</span>
      </span>
    </a>
  );
}

/**
 * The top bar: the mark and a wide-set wordmark, a glass pill with two menus and one direct link, then the
 * source link and the one action. Menus open on click or hover, and close on Escape or a click elsewhere.
 * On phones the same links live in a sheet behind the menu button.
 */
export function Nav() {
  const [open, setOpen] = useState<string | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const timer = useRef<number>();
  const reduce = useReducedMotion();

  useEffect(() => {
    if (!open) return;
    const key = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(null);
    const away = (e: PointerEvent) => !root.current?.contains(e.target as Node) && setOpen(null);
    document.addEventListener('keydown', key);
    document.addEventListener('pointerdown', away);
    return () => {
      document.removeEventListener('keydown', key);
      document.removeEventListener('pointerdown', away);
    };
  }, [open]);

  const hover = (label: string | null) => (e: React.PointerEvent) => {
    if (e.pointerType !== 'mouse') return;
    window.clearTimeout(timer.current);
    if (label) setOpen(label);
    else timer.current = window.setTimeout(() => setOpen(null), 140);
  };
  const close = () => setOpen(null);
  const pop = reduce
    ? { initial: { opacity: 0 }, animate: { opacity: 1 }, exit: { opacity: 0 }, transition: { duration: 0.12 } }
    : { initial: { opacity: 0, y: -6, scale: 0.98 }, animate: { opacity: 1, y: 0, scale: 1 }, exit: { opacity: 0, y: -4, scale: 0.98 }, transition: spring.snappy };

  return (
    <header className="fixed inset-x-0 top-0 z-50">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-28 bg-gradient-to-b from-background/90 via-background/50 to-transparent backdrop-blur-md [mask-image:linear-gradient(to_bottom,black_45%,transparent)]"
      />
      <div ref={root} className="relative mx-auto max-w-[1320px] px-4 sm:px-8">
        <div className="flex h-[76px] items-center justify-between gap-4">
          <Link to="/" aria-label="Axiom home" className="flex shrink-0 items-center gap-3 rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-ring">
            <LogoMark className="h-8 w-8 drop-shadow-[0_0_12px_hsl(var(--primary)/0.55)]" />
            <span translate="no" className="lp-silver text-[0.95rem] font-semibold tracking-[0.34em]">
              AXIOM
            </span>
          </Link>

          <nav aria-label="Page" className="lp-navpill hidden rounded-full p-1 md:block">
            <ul className="flex items-center">
              {NAV_MENUS.map(menu => {
                const isOpen = open === menu.label;
                const id = `menu-${menu.label.toLowerCase()}`;
                return (
                  <li key={menu.label} className="relative" onPointerEnter={hover(menu.label)} onPointerLeave={hover(null)}>
                    <button
                      type="button"
                      aria-expanded={isOpen}
                      aria-controls={id}
                      onClick={() => setOpen(isOpen ? null : menu.label)}
                      className={cn(
                        'flex items-center gap-1.5 rounded-full px-4 py-2 text-small font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring',
                        isOpen ? 'bg-white/[0.08] text-foreground' : 'text-foreground/75 hover:text-foreground',
                      )}
                    >
                      {menu.label}
                      <ChevronDown aria-hidden className={cn('h-3.5 w-3.5 transition-transform duration-200', isOpen && 'rotate-180')} />
                    </button>
                    <AnimatePresence>
                      {isOpen && (
                        <motion.div {...pop} style={{ x: '-50%' }} id={id} className="absolute left-1/2 top-full z-10 w-[372px] origin-top pt-3">
                          <div className="lp-menu rounded-2xl p-2">
                            {menu.items.map(item => (
                              <MenuItem key={item.href} item={item} onPick={close} />
                            ))}
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </li>
                );
              })}
              <li>
                <a
                  href="#honest"
                  className="block rounded-full px-4 py-2 text-small font-medium text-foreground/75 outline-none transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
                >
                  Results
                </a>
              </li>
            </ul>
          </nav>

          <div className="flex items-center gap-2">
            <a
              href={REPO}
              target="_blank"
              rel="noreferrer"
              aria-label="Source code on GitHub"
              className="lp-ghost hidden h-9 w-9 items-center justify-center rounded-full text-foreground/80 outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring sm:flex"
            >
              <Github aria-hidden className="h-4 w-4" />
            </a>
            <StartLink size="sm" />
            <button
              type="button"
              aria-label={open === 'mobile' ? 'Close menu' : 'Open menu'}
              aria-expanded={open === 'mobile'}
              aria-controls="menu-mobile"
              onClick={() => setOpen(open === 'mobile' ? null : 'mobile')}
              className="lp-ghost flex h-9 w-9 items-center justify-center rounded-full outline-none focus-visible:ring-2 focus-visible:ring-ring md:hidden"
            >
              {open === 'mobile' ? <X aria-hidden className="h-4 w-4" /> : <Menu aria-hidden className="h-4 w-4" />}
            </button>
          </div>
        </div>

        <AnimatePresence>
          {open === 'mobile' && (
            <motion.nav {...pop} id="menu-mobile" aria-label="Menu" className="lp-menu max-h-[calc(100dvh-96px)] overflow-y-auto rounded-3xl p-2 md:hidden">
              {NAV_MENUS.map(menu => (
                <div key={menu.label} className="p-1">
                  <p className="px-3 pb-1 pt-3 text-caption font-medium uppercase tracking-[0.14em] text-primary">{menu.label}</p>
                  {menu.items.map(item => (
                    <MenuItem key={item.href} item={item} onPick={close} />
                  ))}
                </div>
              ))}
              <a href="#honest" onClick={close} className="mx-1 mb-1 block rounded-xl px-3 py-3 text-body font-medium hover:bg-white/[0.05]">
                Results
              </a>
            </motion.nav>
          )}
        </AnimatePresence>
      </div>
    </header>
  );
}
