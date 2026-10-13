import { useState } from 'react';
import { KeyRound } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { getToken, setToken } from '@/lib/api';

/** Lets the owner paste the backend's AXIOM_API_TOKEN (kept in this browser only, never in the bundle). */
export function TokenDialog() {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState('');
  const hasToken = getToken() !== '';

  return (
    <Dialog open={open} onOpenChange={o => { setOpen(o); if (o) setValue(getToken()); }}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="API token" className={`h-8 w-8 ${hasToken ? 'text-primary' : 'text-muted-foreground hover:text-foreground'}`}>
          <KeyRound className="h-3.5 w-3.5" />
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="text-h3">API token</DialogTitle>
          <DialogDescription className="text-small">
            Needed for actions that change state (approve, watchlist, paper trades) when the backend sets <code className="rounded-sm bg-muted px-1 font-mono text-caption">AXIOM_API_TOKEN</code>. It is stored only in this browser.
          </DialogDescription>
        </DialogHeader>
        <Input type="password" value={value} onChange={e => setValue(e.target.value)} placeholder="Paste token…" name="api-token" aria-label="API token" className="font-mono text-small" autoComplete="off" spellCheck={false} />
        <div className="flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={() => { setToken(''); setValue(''); setOpen(false); }}>Clear</Button>
          <Button size="sm" onClick={() => { setToken(value.trim()); setOpen(false); }}>Save</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
