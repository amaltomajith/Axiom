import { siFastapi, siGooglegemini, siGooglesheets, siModelcontextprotocol, siNotion, siOllama, siOpenrouter, siReact } from 'simple-icons';

/**
 * Logos only, directly under the hero. Marks come from the simple-icons package; Groq and Slack are not in it,
 * so they are left out instead of being redrawn by hand. This is a "runs on" list, not a customer wall:
 * there are no customers to claim.
 */
const ICONS = [siGooglegemini, siOllama, siOpenrouter, siModelcontextprotocol, siNotion, siGooglesheets, siFastapi, siReact];

export function LogoWall() {
  return (
    <section aria-label="Runs on" className="border-y border-border">
      <ul className="mx-auto flex max-w-[1200px] flex-wrap items-center justify-center gap-x-12 gap-y-6 px-4 py-9 sm:px-6">
        {ICONS.map(icon => (
          <li key={icon.slug} className="text-muted-foreground transition-colors hover:text-foreground">
            <svg viewBox="0 0 24 24" role="img" aria-label={icon.title} className="h-6 w-auto" fill="currentColor">
              <title>{icon.title}</title>
              <path d={icon.path} />
            </svg>
          </li>
        ))}
      </ul>
    </section>
  );
}
