import { useEffect } from 'react';
import { Faq } from '@/landing/Faq';
import { Features } from '@/landing/Features';
import { FinalCta, Footer } from '@/landing/Footer';
import { Hero } from '@/landing/Hero';
import { Honest } from '@/landing/Honest';
import { Modes } from '@/landing/Modes';
import { Nav } from '@/landing/Nav';
import { Showcase } from '@/landing/Showcase';
import { Steps } from '@/landing/Steps';
import { Trust } from '@/landing/Trust';

/** Always dark: the blue light and the globe are drawn for a near-black ground. */
export default function Landing() {
  useEffect(() => {
    document.title = 'Axiom: a trading partner that thinks first';
  }, []);
  return (
    <div className="dark landing min-h-[100dvh] overflow-x-clip bg-background text-foreground">
      <a href="#safety" className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-card focus:px-3 focus:py-2 focus:shadow-md">
        Skip to content
      </a>
      <Nav />
      <main>
        <Hero />
        <Trust />
        <Features />
        <Steps />
        <Modes />
        <Showcase />
        <Honest />
        <Faq />
        <FinalCta />
      </main>
      <Footer />
    </div>
  );
}
