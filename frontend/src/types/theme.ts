/**
 * UI-only types. Anything that represents backend/business state belongs
 * to a TanStack Query hook's inferred type (services/api/), never here --
 * see ARCHITECTURE.md section 2's "React only renders application state,
 * never invents it" rule.
 */

export type ThemeName = "light" | "dark" | "jarvis";
