import { describe, expect, it } from 'vitest';
import { cn } from '@/lib/utils';

describe('cn (tailwind-merge with the custom type scale)', () => {
  it('keeps a text colour when a custom font-size class follows it', () => {
    for (const size of ['display', 'h1', 'h2', 'h3', 'body', 'small', 'caption']) {
      const out = cn('text-primary-foreground', `text-${size}`);
      expect(out).toContain('text-primary-foreground');
      expect(out).toContain(`text-${size}`);
    }
  });

  it('still lets a later colour replace an earlier colour, and a later size replace an earlier size', () => {
    expect(cn('text-muted-foreground', 'text-foreground')).toBe('text-foreground');
    expect(cn('text-small', 'text-h3')).toBe('text-h3');
  });
});
