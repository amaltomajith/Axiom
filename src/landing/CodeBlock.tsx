import { useState } from 'react';
import { Check, Copy } from 'lucide-react';
import { Button } from '@/components/ui/button';

/** Copyable code. If the clipboard is blocked the text is still selectable, so failure is silent and harmless. */
export function CodeBlock({ code, label }: { code: string; label: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      /* clipboard unavailable: the user can still select the text */
    }
  };
  return (
    <div className="relative min-w-0 max-w-full rounded-md border border-border bg-muted">
      <Button variant="ghost" size="icon-sm" onClick={copy} aria-label={`Copy ${label}`} className="absolute right-2 top-2">
        {copied ? <Check className="text-success" /> : <Copy />}
      </Button>
      <pre className="overflow-x-auto p-4 pr-12 font-mono text-caption leading-relaxed" tabIndex={0} aria-label={label}>
        {code}
      </pre>
    </div>
  );
}
