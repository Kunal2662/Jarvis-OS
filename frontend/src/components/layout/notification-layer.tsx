/**
 * Reserved DesktopShell region for the future, persistent Notification
 * Center panel (built on the already-shipped `core/notification-framework.ts`
 * store data, not yet rendered as a panel). Distinct from the ephemeral
 * toast surface, which `providers/notification-provider.tsx` already
 * renders app-wide via `<Toaster />` -- this layer is not a duplicate of
 * that, it's the anchor point for the list view a future task group
 * builds. Renders nothing today.
 */
export function NotificationLayer() {
  return null;
}
