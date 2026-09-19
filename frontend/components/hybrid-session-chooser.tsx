import { Layers } from "lucide-react";
import { Button } from "./ui/button";

export function HybridSessionChooser({
  onUseDemo,
  onUseMicrosoft,
}: {
  onUseDemo: () => void;
  onUseMicrosoft: () => void;
}) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-muted/30 px-6 py-12">
      <section className="w-full max-w-md rounded-2xl border bg-background p-8 shadow-sm sm:p-10">
        <div className="mb-10 flex items-center gap-3 font-semibold">
          <Layers className="size-6" aria-hidden="true" />
          Switchboard
        </div>
        <h1 className="text-2xl font-semibold tracking-tight">Choose how to continue</h1>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">
          Explore an isolated fictional workspace, or use your configured Microsoft employee
          account.
        </p>
        <Button className="mt-8 w-full" size="lg" onClick={onUseDemo}>
          Try the demo
        </Button>
        <Button className="mt-3 w-full" size="lg" variant="outline" onClick={onUseMicrosoft}>
          Sign in with Microsoft
        </Button>
      </section>
    </main>
  );
}
