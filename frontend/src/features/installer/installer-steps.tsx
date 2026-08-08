import {
  Check,
  CircleAlert,
  CircleCheck,
  CircleX,
  Cpu,
  Gauge,
  HardDrive,
  MemoryStick,
  Mic,
  Monitor,
  Shield,
  Sparkles,
  User,
  Wifi,
  WifiOff,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SkeletonRows } from "@/components/common/skeleton";
import { CheckRow } from "@/features/installer/check-row";
import { useInstallerStore } from "@/features/installer/installer-store";
import type { HardwareProfile, InstallationPlan } from "@/features/installer/installer-types";

/**
 * The installer's individual steps -- M22 Task Group A.
 *
 * Two rules run through all of them:
 *
 * 1. **An unmeasured value renders as "Not detected", never as a
 *    number.** The Python side reports `null` for anything it could not
 *    probe (see `jarvis/installer/hardware.py`), and this UI is the
 *    other half of that contract. A GPU row reading "Not detected" with
 *    the reason underneath is honest; "0 GB" is not.
 * 2. **A personal user is never shown a technical control.**
 *    `ARCHITECTURE.md` §22.11 — and the payload they receive genuinely
 *    lacks the fields, so there is nothing here to accidentally render.
 */

// --- Shared ----------------------------------------------------------

function StepHeading({ title, blurb }: { title: string; blurb: string }) {
  return (
    <header className="flex flex-col gap-1.5">
      <h2 className="font-semibold text-card-title">{title}</h2>
      <p className="text-muted-foreground text-secondary">{blurb}</p>
    </header>
  );
}

/** One measured fact. `value === null` is the "we could not measure
 *  this" case and is rendered as such, deliberately un-styled as an
 *  error — a missing sensor is not a fault. */
function Fact({
  icon: Icon,
  label,
  value,
  hint,
}: {
  icon: LucideIcon;
  label: string;
  value: string | null;
  hint?: string;
}) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-border/60 bg-card p-3">
      <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="text-muted-foreground text-xs">{label}</p>
        <p className={`truncate font-medium ${value === null ? "text-muted-foreground" : ""}`}>
          {value ?? "Not detected"}
        </p>
        {hint && <p className="text-muted-foreground text-xs">{hint}</p>}
      </div>
    </div>
  );
}

function formatGb(bytes: number | null): string | null {
  return bytes === null ? null : `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}

// --- Steps -----------------------------------------------------------

export function WelcomeStep() {
  return (
    <div className="flex flex-col gap-4">
      <StepHeading
        title="Welcome to JARVIS"
        blurb="A local-first AI assistant for your desktop. This installer will check your device and set JARVIS up to suit it."
      />
      <ul className="flex flex-col gap-2 text-secondary">
        {[
          "Runs on your machine — your data stays with you.",
          "Works without an internet connection.",
          "Tunes itself to your hardware automatically.",
        ].map((line) => (
          <li key={line} className="flex items-start gap-2">
            <Check className="mt-0.5 size-4 shrink-0 text-emerald-500" aria-hidden="true" />
            {line}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function LicenseStep() {
  const accepted = useInstallerStore((s) => s.licenseAccepted);
  const acceptLicense = useInstallerStore((s) => s.acceptLicense);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <StepHeading title="License agreement" blurb="Please read and accept to continue." />
      <div
        className="min-h-0 flex-1 overflow-auto rounded-lg border border-border/60 bg-muted/30 p-4 text-secondary"
        tabIndex={0}
        role="region"
        aria-label="License agreement text"
      >
        <p className="font-medium">JARVIS OS — Proprietary License</p>
        <p className="pt-2 text-muted-foreground">
          This software is provided under a proprietary license. Installing it means you accept
          the terms distributed with this package. The software is provided &ldquo;as is&rdquo;,
          without warranty of any kind, express or implied.
        </p>
        <p className="pt-2 text-muted-foreground">
          JARVIS processes your data locally by default. Optional cloud features send data to
          third-party providers only when you enable them and supply your own credentials.
        </p>
      </div>
      <label className="flex items-center gap-2.5">
        <input
          type="checkbox"
          checked={accepted}
          onChange={(event) => acceptLicense(event.target.checked)}
          className="size-4 accent-primary"
        />
        <span className="text-secondary">I accept the license agreement</span>
      </label>
    </div>
  );
}

export function LocationStep({ defaultLocation }: { defaultLocation: string }) {
  const location = useInstallerStore((s) => s.installLocation);
  const setLocation = useInstallerStore((s) => s.setLocation);

  return (
    <div className="flex flex-col gap-4">
      <StepHeading
        title="Where should JARVIS live?"
        blurb="This folder holds the application, your local AI model and your data."
      />
      <label className="flex flex-col gap-1.5">
        <span className="text-muted-foreground text-xs">Installation folder</span>
        <Input
          value={location ?? defaultLocation}
          onChange={(event) => setLocation(event.target.value)}
          aria-label="Installation folder"
          spellCheck={false}
        />
      </label>
      {(location ?? defaultLocation).trim() === "" ? (
        // Continue is disabled while this is blank; saying so beats a
        // dead button with no explanation.
        <p className="text-amber-600 text-xs dark:text-amber-500">
          Enter a folder to continue.
        </p>
      ) : (
        <p className="text-muted-foreground text-xs">
          This location needs no administrator rights. Free space is checked on its drive in the
          next step.
        </p>
      )}
    </div>
  );
}

export function AccountStep() {
  const accountType = useInstallerStore((s) => s.accountType);
  const setAccountType = useInstallerStore((s) => s.setAccountType);

  const options = [
    {
      key: "personal" as const,
      icon: User,
      title: "Personal",
      blurb: "JARVIS configures itself. Nothing technical to manage.",
      points: ["Automatic tuning", "Automatic model choice", "Automatic voice setup"],
    },
    {
      key: "administrator" as const,
      icon: Shield,
      title: "Administrator",
      blurb: "Everything in Personal, plus control over providers and budgets.",
      points: ["Provider management", "API keys and budgets", "Calibration policies"],
    },
  ];

  return (
    <div className="flex flex-col gap-4">
      <StepHeading
        title="How will you use JARVIS?"
        blurb="Both get the same features. The difference is how much you manage."
      />
      <div className="grid gap-3 sm:grid-cols-2" role="radiogroup" aria-label="Account type">
        {options.map((option) => {
          const selected = accountType === option.key;
          return (
            <button
              key={option.key}
              type="button"
              role="radio"
              aria-checked={selected}
              // Without this the accessible name is the whole card --
              // icon, title, blurb and three bullets, ~40 words read
              // aloud on focus. It also made the two options ambiguous
              // to match, since the Administrator card's blurb contains
              // the word "Personal". The label names the choice; the
              // description carries the detail.
              aria-label={option.title}
              aria-describedby={`account-${option.key}-detail`}
              onClick={() => setAccountType(option.key)}
              className={`flex flex-col gap-2 rounded-lg border p-4 text-left transition-colors ${
                selected ? "border-primary bg-primary/5" : "border-border/60 hover:border-border"
              }`}
            >
              <option.icon className="size-5 text-muted-foreground" aria-hidden="true" />
              <span className="font-medium">{option.title}</span>
              <span id={`account-${option.key}-detail`} className="text-muted-foreground text-xs">
                {option.blurb}
              </span>
              <ul className="flex flex-col gap-1 pt-1">
                {option.points.map((point) => (
                  <li key={point} className="flex items-center gap-1.5 text-muted-foreground text-xs">
                    <Check className="size-3 shrink-0" aria-hidden="true" />
                    {point}
                  </li>
                ))}
              </ul>
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function HardwareStep({ plan, scanning, error }: { plan: InstallationPlan | null; scanning: boolean; error: string | null }) {
  if (scanning || (!plan && !error)) {
    return (
      <div className="flex flex-col gap-4">
        <StepHeading title="Checking your device" blurb="This takes a few seconds." />
        <SkeletonRows rows={4} label="Scanning hardware" />
      </div>
    );
  }

  if (error || !plan) {
    return (
      <div className="flex flex-col gap-4">
        <StepHeading title="Checking your device" blurb="The scan could not complete." />
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-4">
          <p className="text-secondary">{error ?? "No hardware information was returned."}</p>
        </div>
      </div>
    );
  }

  return <HardwareFacts hardware={plan.hardware} />;
}

function HardwareFacts({ hardware }: { hardware: HardwareProfile }) {
  const gpu = hardware.gpus[0] ?? null;

  return (
    <div className="flex flex-col gap-4">
      <StepHeading title="Your device" blurb="Here is what JARVIS found." />

      <div className="grid gap-2 sm:grid-cols-2">
        <Fact icon={Cpu} label="Processor" value={hardware.cpu.model} hint={
          hardware.cpu.physical_cores
            ? `${hardware.cpu.physical_cores} cores`
            : undefined
        } />
        <Fact icon={MemoryStick} label="Memory" value={`${hardware.memory.total_gb.toFixed(1)} GB`} />
        <Fact
          icon={Monitor}
          label="Graphics"
          value={gpu?.name ?? null}
          hint={gpu?.vram_bytes ? `${formatGb(gpu.vram_bytes)} of graphics memory` : undefined}
        />
        <Fact
          icon={HardDrive}
          label="Free space"
          value={`${hardware.storage.free_gb.toFixed(0)} GB`}
          hint={hardware.storage.path}
        />
        <Fact
          icon={hardware.internet ? Wifi : WifiOff}
          label="Internet"
          value={hardware.internet === null ? null : hardware.internet ? "Connected" : "Not connected"}
        />
        <Fact
          icon={Sparkles}
          label="Neural accelerator"
          value={hardware.npu}
        />
      </div>

      {hardware.notes.length > 0 && (
        <div className="flex flex-col gap-1 rounded-lg border border-border/60 bg-muted/30 p-3">
          {/* Explains each "Not detected" rather than leaving it bare —
              a gap the user understands is not alarming. */}
          {hardware.notes.map((note) => (
            <p key={note} className="text-muted-foreground text-xs">
              {note}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

export function CalibrationStep({ plan }: { plan: InstallationPlan }) {
  const { calibration } = plan;
  const isAdmin = plan.account_type === "administrator";

  const profileCopy: Record<string, string> = {
    performance: "JARVIS will use this device's full capability.",
    balanced: "JARVIS will balance speed against leaving your device responsive.",
    conservative: "JARVIS will keep its footprint small on this device.",
  };

  return (
    <div className="flex flex-col gap-4">
      <StepHeading title="Tuned for your device" blurb={profileCopy[calibration.performance_profile]} />

      <div className="flex items-center gap-4 rounded-lg border border-border/60 bg-card p-4">
        <Gauge className="size-8 shrink-0 text-primary" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-widget-title tabular-nums">{calibration.score}/100</p>
          <p className="text-muted-foreground text-xs">AI capability score</p>
        </div>
      </div>

      {/* Administrator only: the per-component breakdown is technical
          configuration detail, which §22.11 keeps out of a personal
          install. The payload does not contain it either. */}
      {isAdmin && calibration.components && (
        <ul className="flex flex-col gap-2">
          {calibration.components.map((component) => (
            <li key={component.name} className="flex flex-col gap-1 rounded-lg border border-border/60 p-3">
              <div className="flex items-baseline justify-between gap-2">
                <span className="font-medium text-secondary">{component.name}</span>
                <span className="text-muted-foreground text-xs tabular-nums">
                  {component.points} / {component.maximum}
                </span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-muted" role="presentation">
                <div
                  className="h-full rounded-full bg-primary"
                  style={{ width: `${(component.points / component.maximum) * 100}%` }}
                />
              </div>
              <span className="text-muted-foreground text-xs">{component.detail}</span>
            </li>
          ))}
        </ul>
      )}

      {calibration.missing_inputs.length > 0 && (
        <div className="rounded-lg border border-border/60 bg-muted/30 p-3">
          <p className="pb-1 font-medium text-muted-foreground text-xs uppercase tracking-wide">
            Not measured
          </p>
          {calibration.missing_inputs.map((entry) => (
            <p key={entry} className="text-muted-foreground text-xs">
              {entry}
            </p>
          ))}
        </div>
      )}

      {calibration.warnings.map((warning) => (
        <p key={warning} className="flex items-start gap-2 text-amber-600 text-xs dark:text-amber-500">
          <CircleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          {warning}
        </p>
      ))}
    </div>
  );
}

export function ModelStep({ plan }: { plan: InstallationPlan }) {
  const model = plan.recommended_model;

  if (!model) {
    return (
      <div className="flex flex-col gap-4">
        <StepHeading
          title="Local AI"
          blurb="This device is below the minimum for a local model."
        />
        <p className="rounded-lg border border-border/60 bg-muted/30 p-4 text-secondary">
          JARVIS will use cloud AI where it is available. Everything else works as normal.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <StepHeading title="Local AI" blurb="Chosen to suit your device. You can change this later." />
      <div className="flex flex-col gap-2 rounded-lg border border-primary/40 bg-primary/5 p-4">
        <div className="flex items-baseline justify-between gap-2">
          <span className="font-semibold text-card-title">{model.label}</span>
          <span className="text-muted-foreground text-xs">
            about {model.approximate_download_gb.toFixed(1)} GB
          </span>
        </div>
        <p className="text-muted-foreground text-secondary">{model.description}</p>
        {/* Administrator only — a model id is provider detail. */}
        {model.model_id && (
          <p className="pt-1 font-mono text-muted-foreground text-xs">{model.model_id}</p>
        )}
      </div>
      <p className="text-muted-foreground text-xs">
        Nothing is downloaded during this step. The model is fetched on first launch.
      </p>
    </div>
  );
}

export function VoiceStep({ plan }: { plan: InstallationPlan }) {
  const { voice } = plan;

  return (
    <div className="flex flex-col gap-4">
      <StepHeading
        title="Voice"
        blurb={`JARVIS speaks with one voice everywhere${voice.can_test_offline ? ", and it works offline" : ""}.`}
      />

      <div className="flex items-center gap-4 rounded-lg border border-border/60 bg-card p-4">
        <Mic className="size-6 shrink-0 text-primary" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p className="font-medium">{voice.identity_name}</p>
          <p className="text-muted-foreground text-xs">
            about {voice.total_download_mb} MB of voice components
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          // Honest about what it can do today: the components are not
          // installed yet, so there is nothing to play. Disabled with a
          // reason beats a button that appears to work and does not.
          disabled
          title="Available on first launch, once voice components are installed"
        >
          Test voice
        </Button>
      </div>

      {/* Administrator only: these name providers. */}
      {voice.components && (
        <ul className="flex flex-col gap-2">
          {voice.components.map((component) => (
            <li
              key={component.key}
              className="flex items-start gap-3 rounded-lg border border-border/60 p-3"
            >
              {component.enabled ? (
                <CircleCheck className="mt-0.5 size-4 shrink-0 text-emerald-500" aria-hidden="true" />
              ) : (
                <CircleX className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
              )}
              <div className="min-w-0 flex-1">
                <p className="font-medium text-secondary">{component.label}</p>
                <p className="text-muted-foreground text-xs">{component.reason}</p>
              </div>
              {component.approximate_download_mb > 0 && (
                <span className="shrink-0 text-muted-foreground text-xs">
                  {component.approximate_download_mb} MB
                </span>
              )}
            </li>
          ))}
        </ul>
      )}

      {voice.notes.map((note) => (
        <p key={note} className="text-muted-foreground text-xs">
          {note}
        </p>
      ))}
    </div>
  );
}

export function SummaryStep({ plan }: { plan: InstallationPlan }) {
  const blocking = plan.validation.results.filter((result) => result.blocking);

  return (
    <div className="flex flex-col gap-4">
      <StepHeading
        title={plan.validation.can_install ? "Ready to install" : "Cannot install yet"}
        blurb={
          plan.validation.can_install
            ? "Here is what will happen."
            : "These need attention before JARVIS can be installed."
        }
      />

      <dl className="grid gap-2 sm:grid-cols-2">
        <Fact icon={HardDrive} label="Location" value={plan.install_location} />
        <Fact
          icon={plan.account_type === "administrator" ? Shield : User}
          label="Account"
          value={plan.account_type === "administrator" ? "Administrator" : "Personal"}
        />
        <Fact icon={Sparkles} label="Local AI" value={plan.recommended_model?.label ?? "Cloud only"} />
        <Fact icon={Mic} label="Voice" value={plan.voice.identity_name} />
      </dl>

      <div className="rounded-lg border border-border/60 p-3">
        <p className="pb-1 font-medium text-muted-foreground text-xs uppercase tracking-wide">
          Pre-installation checks
        </p>
        <ul>
          {plan.validation.results.map((result) => (
            <CheckRow
              key={result.key}
              label={result.label}
              verdict={result.verdict}
              detail={result.detail}
            />
          ))}
        </ul>
      </div>

      {blocking.length > 0 && (
        <p className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-secondary">
          Resolve the items marked in red, then return to this step.
        </p>
      )}
    </div>
  );
}

// `InstallStep` and `ReadyStep` lived here in M22 Task Group A as
// honest placeholders -- one said the installation engine did not exist
// yet, the other's buttons were disabled because nothing stood behind
// them. Task Group B built the engine and this milestone wired it up, so
// both are superseded by `install-progress-step.tsx` and
// `completion-step.tsx`, which render real provisioning state. Removed
// rather than left alongside: two components for one step is how a
// wizard ends up rendering the wrong one.

