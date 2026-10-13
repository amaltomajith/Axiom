import { CircleCheck, CircleX } from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Button } from '@/components/ui/button';
import { DefList } from '@/components/kit/DefList';
import type { Health } from '@/lib/types';

/** Everything about "what is this connected to" in one place, replacing three header chips. */
export function StatusPopover({ health, offline }: { health: Health | undefined; offline: boolean }) {
  const ok = Boolean(health?.ok) && !offline;
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="sm" aria-label={ok ? 'Backend connected' : 'Backend offline'} className="gap-2 px-2.5">
          {ok ? <CircleCheck className="text-success" /> : <CircleX className="text-destructive" />}
          <span className="hidden sm:inline">{ok ? 'Connected' : 'Offline'}</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80">
        {health ? (
          <>
            <p className="text-small font-medium">Connections</p>
            <DefList
              className="mt-2"
              items={[
                { label: 'Prices', value: `${health.market_data}, daily bars` },
                { label: 'News', value: health.news.replace(/_/g, ' ') },
                { label: 'Models', value: health.llm_chain.length ? health.llm_chain.join(', ') : 'none' },
                { label: 'Actions', value: health.actions_executor === 'dry_run' ? 'Dry run' : 'Live' },
                { label: 'Protected', value: health.auth_required ? 'Token required' : 'Open (local)' },
              ]}
            />
            {health.actions_executor === 'dry_run' && (
              <p className="mt-3 text-caption text-muted-foreground">Dry run means approved actions are recorded here and nothing is sent to Notion, Sheets or Slack.</p>
            )}
          </>
        ) : (
          <div className="text-small">
            <p className="font-medium text-destructive">Backend unreachable</p>
            <p className="mt-1 text-muted-foreground">
              Start it with <code className="rounded-sm bg-muted px-1 font-mono text-caption">uv run python -m axiom.api</code> inside the backend folder.
            </p>
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}
