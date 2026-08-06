import {
  CircleAlert,
  CircleCheck,
  CircleX,
  Clock,
  Download,
  Gauge,
  Loader2,
  Mic,
  RotateCw,
  Sparkles,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useMemo } from "react";
import {
  DOWNLOAD_STATE_LABEL,
  formatBytes,
  formatDuration,
  formatSpeed,
  groupByKind,
  selectIsResuming,
  useProvisioningStore,
  type DownloadItem,
} from "@/features/installer/provisioning-store";
import type { DownloadItemState } from "@/features/installer/provisioning-types";

/**
 * The installation screen -- M22 installer UI.
 *
 * Everything on it comes from the backend's event stream. The only two
 * computed values, speed and time remaining, are derived from the
 * authoritative byte counts (see `provisioning-store.ts` for why the
 * engine does not emit them).
 *
 * **Nothing here can leak an internal identifier**, because the personal
 * payload does not contain one: the stream carries `name` ("Local AI"),
 * never `key`, and carries no URL or filesystem path at all. This
 * component renders what it is given rather than filtering — filtering
 * in the UI would imply the data arrives and is hidden, which is the
 * weaker guarantee.
 */

const KIND_ICON: Record<string, LucideIcon> = {
  model: Sparkles,
  voice: Mic,
};

const STATE_STYLE: Record<DownloadItemState, { icon: LucideIcon; className: string; spin?: boolean }> = {
  queued: { icon: Clock, className: "text-muted-foreground" },
  running: { icon: Download, className: "text-primary", spin: false },
  paused: { icon: Clock, className: "text-muted-foreground" },
  verifying: { icon: Loader2, className: "text-primary", spin: true },
  completed: { icon: CircleCheck, className: "text-emerald-500" },
  skipped: { icon: CircleCheck, className: "text-muted-foreground" },
  failed: { icon: CircleX, className: "text-destructive" },
  cancelled: { icon: CircleAlert, className: "text-amber-500" },
};

function DownloadRow({ item }: { item: DownloadItem }) {
  const style = STATE_STYLE[item.state];
  const KindIcon = KIND_ICON[item.kind] ?? Download;
  const StateIcon = style.icon;

  return (
    <li className="flex items-center gap-3 py-2">
      <KindIcon className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />

      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <span className="truncate font-medium text-secondary">{item.name}</span>
          <span className="shrink-0 text-muted-foreground text-xs">
            {DOWNLOAD_STATE_LABEL[item.state]}
          </span>
        </div>

        {item.state === "running" && (
          <div
            className="mt-1 h-1 overflow-hidden rounded-full bg-muted"
            role="progressbar"
            aria-label={`${item.name} download progress`}
            // An unknown total gives an indeterminate bar rather than a
            // fabricated percentage.
            aria-valuenow={item.percent ?? undefined}
            aria-valuemin={0}
            aria-valuemax={100}
          >
            <div
              className={`h-full rounded-full bg-primary ${item.percent === null ? "w-1/3 animate-pulse" : "transition-[width]"}`}
              style={item.percent === null ? undefined : { width: `${item.percent}%` }}
            />
          </div>
        )}
      </div>

      <StateIcon
        className={`size-4 shrink-0 ${style.className} ${style.spin ? "animate-spin" : ""}`}
        aria-label={DOWNLOAD_STATE_LABEL[item.state]}
      />
    </li>
  );
}

function DownloadGroup({ title, items }: { title: string; items: DownloadItem[] }) {
  if (items.length === 0) return null;
  return (
    <section className="flex flex-col">
      <h3 className="pb-0.5 font-medium text-muted-foreground text-xs uppercase tracking-wide">
        {title}
      </h3>
      <ul className="divide-y divide-border/60">
        {items.map((item) => (
          <DownloadRow key={item.id} item={item} />
        ))}
      </ul>
    </section>
  );
}

function Stat({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value: string }) {
  return (
    <div className="flex items-center gap-2">
      <Icon className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
      <span className="text-muted-foreground text-xs">{label}</span>
      <span className="ml-auto font-medium tabular-nums text-xs">{value}</span>
    </div>
  );
}

export interface InstallProgressStepProps {
  /** Re-run provisioning. Resumes from the journal, so a retry never
   *  repeats completed work. */
  onRetry: () => void;

  /** Stop the running installation. `null` when the host cannot, in
   *  which case no control is offered — a Cancel button that does
   *  nothing is worse than none. */
  onCancel?: (() => void) | null;
}

export function InstallProgressStep({ onRetry, onCancel = null }: InstallProgressStepProps) {
  const phase = useProvisioningStore((s) => s.phase);
  const label = useProvisioningStore((s) => s.label);
  const percent = useProvisioningStore((s) => s.percent);
  const completedSteps = useProvisioningStore((s) => s.completedSteps);
  const totalSteps = useProvisioningStore((s) => s.totalSteps);
  const bytesDownloaded = useProvisioningStore((s) => s.bytesDownloaded);
  const bytesTotal = useProvisioningStore((s) => s.bytesTotal);
  const speed = useProvisioningStore((s) => s.speedBytesPerSecond);
  const eta = useProvisioningStore((s) => s.etaSeconds);
  const failure = useProvisioningStore((s) => s.failure);
  const resuming = useProvisioningStore(selectIsResuming);
  const downloads = useProvisioningStore((s) => s.downloads);

  // Grouped here rather than in a store selector. `selectDownloadsByKind`
  // builds a new object on every call, and zustand compares selector
  // results by reference -- using it as a hook selector made every render
  // look like a state change and looped until React gave up with
  // "Maximum update depth exceeded". The store keeps `downloads` as a
  // stable array; shaping it for display is the component's job.
  const { models, voices, other } = useMemo(
    () => groupByKind(downloads),
    [downloads],
  );

  const anyDownloads = models.length + voices.length + other.length > 0;

  if (phase === "failed" && failure) {
    return (
      <div className="flex flex-col gap-4">
        <header className="flex flex-col gap-1.5">
          <div className="flex items-center gap-2">
            <CircleX className="size-5 shrink-0 text-destructive" aria-hidden="true" />
            <h2 className="font-semibold text-card-title">{failure.title}</h2>
          </div>
          <p className="text-muted-foreground text-secondary">{failure.detail}</p>
        </header>

        {/* The list stays visible so the user can see what did land --
            "your progress has been saved" is more convincing when the
            completed items are on screen. */}
        {anyDownloads && (
          <div className="flex flex-col gap-3 rounded-lg border border-border/60 p-3">
            <DownloadGroup title="Models" items={models} />
            <DownloadGroup title="Voices" items={voices} />
            <DownloadGroup title="Assets" items={other} />
          </div>
        )}

        {failure.retryable && (
          <Button onClick={onRetry} className="gap-1.5 self-start">
            <RotateCw className="size-4" aria-hidden="true" />
            Continue installation
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-col gap-1.5">
        <h2 className="font-semibold text-card-title">
          {resuming ? "Resuming installation…" : "Setting up JARVIS"}
        </h2>
        {/* One live region for the phase, so a screen reader hears
            "Downloading…" once per change rather than on every byte. */}
        <p className="text-muted-foreground text-secondary" aria-live="polite">
          {label ?? "Preparing…"}
        </p>
      </header>

      <div
        className="h-1.5 overflow-hidden rounded-full bg-muted"
        role="progressbar"
        aria-label="Installation progress"
        aria-valuenow={Math.round(percent)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className="h-full rounded-full bg-primary transition-[width] duration-500"
          style={{ width: `${percent}%` }}
        />
      </div>

      <div className="grid gap-2 sm:grid-cols-2">
        <Stat icon={Gauge} label="Overall" value={`${Math.round(percent)}%`} />
        <Stat
          icon={CircleCheck}
          label="Steps"
          value={`${completedSteps} of ${totalSteps}`}
        />
        <Stat
          icon={Download}
          label="Downloaded"
          value={
            bytesTotal === null
              ? formatBytes(bytesDownloaded)
              : `${formatBytes(bytesDownloaded)} of ${formatBytes(bytesTotal)}`
          }
        />
        <Stat icon={Gauge} label="Speed" value={formatSpeed(speed)} />
        <Stat icon={Clock} label="Time remaining" value={formatDuration(eta)} />
      </div>

      {anyDownloads && (
        <div className="flex flex-col gap-3 rounded-lg border border-border/60 p-3">
          <DownloadGroup title="Models" items={models} />
          <DownloadGroup title="Voices" items={voices} />
          <DownloadGroup title="Assets" items={other} />
        </div>
      )}

      {resuming && (
        <p className="text-muted-foreground text-xs">
          Work already completed is being skipped.
        </p>
      )}

      {/* Cancelling is safe and says so: the journal records completed
          steps, so stopping here loses at most the step in flight. The
          reassurance is the point — without it the honest question
          "will this leave a broken half-installation?" has no answer,
          and the user's alternative is killing the window, which is the
          same stop with none of the cleanup. */}
      {onCancel && (
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={onCancel} className="gap-1.5">
            <CircleX className="size-4" aria-hidden="true" />
            Cancel installation
          </Button>
          <span className="text-muted-foreground text-xs">
            You can continue later from where it stops.
          </span>
        </div>
      )}
    </div>
  );
}
