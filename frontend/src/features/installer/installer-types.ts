/**
 * The installer's data contract -- M22 Task Group A.
 *
 * These types mirror what `python -m jarvis.installer plan` emits. They
 * are hand-written against that command's real output (captured from a
 * live run), not from the roadmap — the same discipline M8 Phase 2
 * established after eleven invented WebSocket event names shipped.
 * `installer-contract.test.ts` pins the shape against a fixture taken
 * from an actual run.
 *
 * **Optionality here is meaningful, not defensive.** Every `| null`
 * below marks a value the installer genuinely could not measure on some
 * machine, and the UI is required to render it as "Not detected" rather
 * than substituting a plausible number. `HardwareProfile.notes`
 * explains each gap in the user's own words.
 *
 * **Personal payloads are structurally smaller.** `calibration.
 * components`, `calibration.resource_limits`, `recommended_model.
 * model_id` and `voice.components` are present only for an
 * administrator, because the Python side omits them entirely rather
 * than sending them for the UI to hide (`ARCHITECTURE.md` §22.11/
 * §22.12). That is why they are optional properties rather than
 * nullable ones — the distinction is "absent" versus "unmeasured".
 */

export type AccountType = "personal" | "administrator";

export type PerformanceProfile = "conservative" | "balanced" | "performance";
export type CloudUsage = "preferred" | "balanced" | "minimal";
export type Verdict = "pass" | "warn" | "fail";

export interface PlatformInfo {
  system: string;
  release: string;
  version: string;
  machine: string;
  python: string;
  is_windows: boolean;
  is_macos: boolean;
  is_linux: boolean;
}

export interface CpuInfo {
  model: string | null;
  physical_cores: number | null;
  logical_cores: number | null;
  max_frequency_mhz: number | null;
  architecture: string;
}

export interface MemoryInfo {
  total_bytes: number;
  available_bytes: number;
  total_gb: number;
}

export interface GpuInfo {
  name: string;
  vram_bytes: number | null;
  vendor: string | null;
  source: string;
}

export interface StorageInfo {
  path: string;
  total_bytes: number;
  free_bytes: number;
  free_gb: number;
}

export interface PowerInfo {
  has_battery: boolean | null;
  on_battery: boolean | null;
  percent: number | null;
}

export interface HardwareProfile {
  platform: PlatformInfo;
  cpu: CpuInfo;
  memory: MemoryInfo;
  storage: StorageInfo;
  gpus: GpuInfo[];
  power: PowerInfo;
  internet: boolean | null;
  temperature_celsius: number | null;
  npu: string | null;
  notes: string[];
  total_vram_bytes: number | null;
}

export interface ScoreComponent {
  name: string;
  points: number;
  maximum: number;
  detail: string;
}

export interface ResourceLimits {
  max_memory_fraction: number;
  max_cpu_fraction: number;
  use_gpu: boolean;
}

export interface ModelRecommendation {
  key: string;
  label: string;
  minimum_ram_gb: number;
  approximate_download_gb: number;
  description: string;
  /** Administrator payloads only. */
  model_id?: string;
}

export interface Calibration {
  score: number;
  performance_profile: PerformanceProfile;
  cloud_usage: CloudUsage;
  missing_inputs: string[];
  warnings: string[];
  recommended_model: ModelRecommendation | null;
  /** Administrator payloads only. */
  components?: ScoreComponent[];
  /** Administrator payloads only. */
  resource_limits?: ResourceLimits;
  /** Administrator payloads only. */
  inputs?: Record<string, unknown>;
}

export interface VoiceComponent {
  key: string;
  label: string;
  role: "tts_local" | "tts_cloud" | "stt_local";
  approximate_download_mb: number;
  required: boolean;
  enabled: boolean;
  reason: string;
}

export interface VoicePlan {
  identity_name: string;
  can_test_offline: boolean;
  total_download_mb: number;
  notes: string[];
  /** Administrator payloads only — these name providers. */
  components?: VoiceComponent[];
  /** Personal payloads only. */
  component_count?: number;
}

export interface ValidationResult {
  key: string;
  label: string;
  verdict: Verdict;
  detail: string;
  blocking: boolean;
}

export interface ValidationReport {
  can_install: boolean;
  results: ValidationResult[];
}

export interface InstallationPlan {
  account_type: AccountType;
  install_location: string;
  hardware: HardwareProfile;
  calibration: Calibration;
  voice: VoicePlan;
  validation: ValidationReport;
  recommended_model: ModelRecommendation | null;
}

/** The wizard's steps, in order. `installer-store.ts` relies on the
 *  ordering for next/back. */
export const INSTALLER_STEPS = [
  "welcome",
  "license",
  "location",
  "account",
  "hardware",
  "calibration",
  "model",
  "voice",
  "summary",
  "install",
  "ready",
] as const;

export type InstallerStep = (typeof INSTALLER_STEPS)[number];

export const STEP_TITLES: Record<InstallerStep, string> = {
  welcome: "Welcome",
  license: "License agreement",
  location: "Installation location",
  account: "Account type",
  hardware: "Checking your device",
  calibration: "Tuning JARVIS",
  model: "Local AI",
  voice: "Voice",
  summary: "Ready to install",
  install: "Installing",
  ready: "All set",
};
