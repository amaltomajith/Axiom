import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Logo } from '@/components/Logo';

export default function NotFound() {
  return (
    <div className="flex min-h-[100dvh] flex-col items-center justify-center bg-background px-6 text-center">
      <Logo />
      <h1 className="mt-10 text-h1">That page does not exist</h1>
      <p className="mt-2 max-w-[44ch] text-body text-muted-foreground">The link may be old, or the address mistyped.</p>
      <div className="mt-6 flex gap-3">
        <Button asChild>
          <Link to="/app">Open terminal</Link>
        </Button>
        <Button asChild variant="secondary">
          <Link to="/">Go to the home page</Link>
        </Button>
      </div>
    </div>
  );
}
