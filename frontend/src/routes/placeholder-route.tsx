import { Construction } from "lucide-react";

/**
 * The one shared "module not built yet" screen every route below renders
 * until its real module ships -- the React equivalent of the shipped
 * PySide6 `coming_soon_view.py`. Never a fake preview of the module's
 * eventual UI, per this phase's explicit "no placeholder business logic"
 * rule -- just an honest, identical statement of fact for every
 * unbuilt route.
 */
export function PlaceholderRoute({ label }: { label: string }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
      <Construction className="size-icon-xl text-muted-foreground" aria-hidden="true" />
      <p className="text-card-title font-bold">{label}</p>
      <p className="max-w-sm text-secondary text-muted-foreground">
        This module hasn't been built yet. It will appear here once its own implementation phase
        ships.
      </p>
    </div>
  );
}
