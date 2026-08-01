import { Toaster as Sonner, type ToasterProps } from "sonner"
import { CircleCheckIcon, InfoIcon, TriangleAlertIcon, OctagonXIcon, Loader2Icon } from "lucide-react"
import { useThemeStore } from "@/stores/theme.store"

const Toaster = ({ ...props }: ToasterProps) => {
  // Not next-themes' own `useTheme()` -- this app has its own Zustand
  // theme store (providers/theme-provider.tsx), not next-themes'
  // provider, so next-themes' hook would silently read its unmounted
  // default instead of the real active theme. "jarvis" maps to sonner's
  // "dark" mode, matching ThemeProvider's own dark-family treatment.
  const theme = useThemeStore((s) => s.theme);
  const sonnerTheme: ToasterProps["theme"] = theme === "light" ? "light" : "dark";

  return (
    <Sonner
      theme={sonnerTheme}
      className="toaster group"
      icons={{
        success: (
          <CircleCheckIcon className="size-4" />
        ),
        info: (
          <InfoIcon className="size-4" />
        ),
        warning: (
          <TriangleAlertIcon className="size-4" />
        ),
        error: (
          <OctagonXIcon className="size-4" />
        ),
        loading: (
          <Loader2Icon className="size-4 animate-spin" />
        ),
      }}
      style={
        {
          "--normal-bg": "var(--popover)",
          "--normal-text": "var(--popover-foreground)",
          "--normal-border": "var(--border)",
          "--border-radius": "var(--radius)",
        } as React.CSSProperties
      }
      toastOptions={{
        classNames: {
          toast: "cn-toast",
        },
      }}
      {...props}
    />
  )
}

export { Toaster }
