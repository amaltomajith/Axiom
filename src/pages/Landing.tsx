import { useEffect } from 'react';
import { Evals } from '@/landing/Evals';
import { FinalCta, Footer } from '@/landing/Footer';
import { Hero } from '@/landing/Hero';
import { Honest } from '@/landing/Honest';
import { LogoWall } from '@/landing/LogoWall';
import { McpSection } from '@/landing/McpSection';
import { Nav } from '@/landing/Nav';
import { StackSection } from '@/landing/StackSection';
import { Walkthrough } from '@/landing/Walkthrough';

export default function Landing() {
  useEffect(() => {
    document.title = 'Axiom: research that shows its work';
  }, []);
  return (
    <div className="min-h-[100dvh] bg-background">
      <a href="#how" className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-card focus:px-3 focus:py-2 focus:shadow-md">
        Skip to content
      </a>
      <Nav />
      <main>
        <Hero />
        <LogoWall />
        <Walkthrough />
        <Honest />
        <Evals />
        <McpSection />
        <StackSection />
        <FinalCta />
      </main>
      <Footer />
    </div>
  );
}
