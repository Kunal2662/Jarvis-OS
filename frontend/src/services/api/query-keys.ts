/**
 * Centralized TanStack Query key factory -- every future feature hook
 * registers its key namespace here instead of inlining ad-hoc array
 * literals, so cache invalidation (`queryClient.invalidateQueries`) stays
 * consistent as feature hooks are added. Empty until a real feature
 * lands; this file's only job right now is establishing the pattern.
 */
export const queryKeys = {
  all: ["jarvis"] as const,
} as const;
