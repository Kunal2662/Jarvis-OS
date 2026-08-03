import { useEffect, useMemo, useRef, useSyncExternalStore, type ChangeEvent } from "react";
import {
  ArrowDown,
  ArrowUp,
  Download,
  GripVertical,
  Maximize2,
  Pin,
  PinOff,
  Plus,
  RotateCcw,
  Upload,
  X,
} from "lucide-react";
import { Reorder, useDragControls } from "motion/react";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { dashboardWidgetRegistry, type DashboardWidgetContribution } from "@/core/dashboard-widget-registry";
import { cn } from "@/lib/utils";
import { useDashboardLayoutStore, type WidgetLayoutEntry } from "@/stores/dashboard-layout.store";
import { isModuleEnabled, useModuleEnablementStore } from "@/stores/module-enablement.store";

/** The 4 grid footprints a widget can cycle through via its Resize
 *  control -- deliberately fixed and small (a 2-column grid only ever
 *  needs "how many of the 2 columns" and "1 or 2 rows tall"), not
 *  arbitrary free-form sizing, which would need real drag-resize
 *  physics this phase doesn't build. */
const SIZE_TIERS: { width: number; height: number }[] = [
  { width: 1, height: 1 },
  { width: 2, height: 1 },
  { width: 1, height: 2 },
  { width: 2, height: 2 },
];

function nextSize(current: { width: number; height: number }): { width: number; height: number } {
  const index = SIZE_TIERS.findIndex((tier) => tier.width === current.width && tier.height === current.height);
  return SIZE_TIERS[(index + 1) % SIZE_TIERS.length] ?? SIZE_TIERS[0];
}

/**
 * The Dashboard's grid renderer (Phase 3, Task Group F) -- registry-
 * and enablement-driven, the same pattern Sidebar/Dock/Status Bar
 * already establish: this component doesn't know or care which
 * widgets are Core JARVIS's own vs a future plugin's contribution, it
 * renders whatever `dashboardWidgetRegistry`
 * (`core/dashboard-widget-registry.ts`) has registered and the user has
 * enabled. Per-widget size/order/pin/visibility is the user's own
 * layout preference (`stores/dashboard-layout.store.ts`), never
 * hardcoded here -- starts empty on a fresh install and self-populates
 * from whatever's actually available, per this milestone's "no fake
 * data" rule applied to layout itself, not just widget content.
 */
export function DashboardGrid() {
  const enabledModuleIds = useModuleEnablementStore((s) => s.enabledModuleIds);
  const order = useDashboardLayoutStore((s) => s.order);
  const entries = useDashboardLayoutStore((s) => s.entries);
  const ensureWidget = useDashboardLayoutStore((s) => s.ensureWidget);
  const resetLayout = useDashboardLayoutStore((s) => s.resetLayout);
  const exportLayout = useDashboardLayoutStore((s) => s.exportLayout);
  const importLayout = useDashboardLayoutStore((s) => s.importLayout);
  const addWidget = useDashboardLayoutStore((s) => s.addWidget);
  const reorderPeers = useDashboardLayoutStore((s) => s.reorderPeers);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Same "re-render on demand" pattern as Sidebar/Dock/StatusBar --
  // ContributionRegistry.getAll() returns a referentially-stable array.
  const contributions = useSyncExternalStore(
    () => () => {},
    () => dashboardWidgetRegistry.getAll(),
  );

  const availableWidgets = useMemo(
    () => contributions.filter((widget) => isModuleEnabled(widget.isCore, widget.moduleId, enabledModuleIds)),
    [contributions, enabledModuleIds],
  );

  // Registers a layout entry the first time a widget becomes available
  // (first run, or a module just got enabled) -- ensureWidget() is a
  // no-op once an entry exists, so this never overwrites a user's own
  // size/order/pin choice on a later render.
  useEffect(() => {
    for (const widget of availableWidgets) {
      ensureWidget(widget.id, widget.defaultSize);
    }
  }, [availableWidgets, ensureWidget]);

  const contributionById = useMemo(() => new Map(availableWidgets.map((w) => [w.id, w])), [availableWidgets]);

  const visibleIds = order.filter((id) => contributionById.has(id) && entries[id]?.visible);
  const pinnedIds = visibleIds.filter((id) => entries[id]?.pinned);
  const unpinnedIds = visibleIds.filter((id) => !entries[id]?.pinned);
  const renderIds = [...pinnedIds, ...unpinnedIds];

  const hiddenWidgets = order
    .filter((id) => contributionById.has(id) && entries[id] && !entries[id].visible)
    .map((id) => contributionById.get(id))
    .filter((widget): widget is DashboardWidgetContribution => widget !== undefined);

  const handleExport = () => {
    const json = exportLayout();
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "jarvis-dashboard-layout.json";
    link.click();
    URL.revokeObjectURL(url);
  };

  const handleImportFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    void file.text().then((text) => {
      try {
        importLayout(text);
      } catch {
        // Malformed file -- importLayout() validates before applying,
        // so a bad file leaves the current layout untouched. No
        // toast/notification wiring exists yet for this to surface
        // through (that's Task Group G's Notification Center); a
        // silent no-op on invalid input is the honest behavior until
        // one does, rather than a fabricated success message.
      }
    });
  };

  return (
    <div className="flex flex-col gap-4">
      {/* No page title here -- `components/layout/header.tsx` already
          renders the active module's displayName ("Dashboard") as the
          page's one <h1>; a second one would be a duplicate landmark
          for screen reader users navigating by heading. */}
      <div className="flex items-center justify-end gap-2">
        <div className="flex items-center gap-1.5">
          {hiddenWidgets.length > 0 && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="sm">
                  <Plus aria-hidden="true" />
                  Add widget
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent>
                {hiddenWidgets.map((widget) => (
                  <DropdownMenuItem key={widget.id} onSelect={() => addWidget(widget.id)}>
                    {widget.title}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
          <Button variant="outline" size="sm" onClick={handleExport}>
            <Download aria-hidden="true" />
            Export
          </Button>
          <Button variant="outline" size="sm" onClick={() => fileInputRef.current?.click()}>
            <Upload aria-hidden="true" />
            Import
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept="application/json"
            onChange={handleImportFile}
            className="sr-only"
            aria-label="Import dashboard layout"
            tabIndex={-1}
          />
          <Button variant="ghost" size="sm" onClick={resetLayout}>
            <RotateCcw aria-hidden="true" />
            Reset
          </Button>
        </div>
      </div>

      {renderIds.length === 0 ? (
        <p className="text-secondary text-muted-foreground">
          No widgets to show. Use "Add widget" to bring one back.
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 sm:auto-rows-[12rem]">
          {/* Two separate Reorder.Group instances (Task Group L), one per
              pin group -- `as="div"`/`className="contents"` so neither
              introduces a wrapper box of its own; their `Reorder.Item`
              children remain direct children of this CSS grid, exactly as
              plain `<WidgetCard>`s were before. Dragging a widget only
              ever reorders it among its own pin-group peers, the same
              constraint the Move up/down buttons already enforce -- drag
              is additive, not a replacement for them. */}
          {pinnedIds.length > 0 && (
            <Reorder.Group
              as="div"
              axis="y"
              className="contents"
              values={pinnedIds}
              onReorder={(order) => reorderPeers(order, true)}
            >
              {pinnedIds.map((id, index) => {
                const contribution = contributionById.get(id);
                const entry = entries[id];
                if (!contribution || !entry) return null;
                return (
                  <WidgetCard
                    key={id}
                    contribution={contribution}
                    entry={entry}
                    isFirst={index === 0}
                    isLast={index === pinnedIds.length - 1}
                  />
                );
              })}
            </Reorder.Group>
          )}
          {unpinnedIds.length > 0 && (
            <Reorder.Group
              as="div"
              axis="y"
              className="contents"
              values={unpinnedIds}
              onReorder={(order) => reorderPeers(order, false)}
            >
              {unpinnedIds.map((id, index) => {
                const contribution = contributionById.get(id);
                const entry = entries[id];
                if (!contribution || !entry) return null;
                return (
                  <WidgetCard
                    key={id}
                    contribution={contribution}
                    entry={entry}
                    isFirst={index === 0}
                    isLast={index === unpinnedIds.length - 1}
                  />
                );
              })}
            </Reorder.Group>
          )}
        </div>
      )}
    </div>
  );
}

function WidgetCard({
  contribution,
  entry,
  isFirst,
  isLast,
}: {
  contribution: DashboardWidgetContribution;
  entry: WidgetLayoutEntry;
  isFirst: boolean;
  isLast: boolean;
}) {
  const resizeWidget = useDashboardLayoutStore((s) => s.resizeWidget);
  const moveWidget = useDashboardLayoutStore((s) => s.moveWidget);
  const togglePin = useDashboardLayoutStore((s) => s.togglePin);
  const removeWidget = useDashboardLayoutStore((s) => s.removeWidget);
  // `dragListener={false}` + a dedicated handle (below) rather than the
  // whole card -- the card is full of its own interactive controls
  // (buttons, and the widget's own real content), so making the entire
  // surface a drag target would fight with clicking any of them.
  const dragControls = useDragControls();

  return (
    <Reorder.Item
      as="div"
      value={entry.id}
      dragListener={false}
      dragControls={dragControls}
      className={cn(
        "h-full",
        entry.width >= 2 ? "sm:col-span-2" : "sm:col-span-1",
        entry.height >= 2 ? "sm:row-span-2" : "sm:row-span-1",
      )}
    >
      <Card role="group" aria-label={contribution.title} className="flex h-full flex-col">
        <CardHeader>
          <CardTitle>{contribution.title}</CardTitle>
          <CardAction>
            <div className="flex items-center gap-0.5">
              <Button
                variant="ghost"
                size="icon-xs"
                aria-label="Drag to reorder"
                className="cursor-grab touch-none active:cursor-grabbing"
                onPointerDown={(event) => dragControls.start(event)}
              >
                <GripVertical aria-hidden="true" />
              </Button>
              <Button
                variant="ghost"
                size="icon-xs"
                aria-label="Move up"
                disabled={isFirst}
                onClick={() => moveWidget(entry.id, "up")}
              >
                <ArrowUp aria-hidden="true" />
              </Button>
              <Button
                variant="ghost"
                size="icon-xs"
                aria-label="Move down"
                disabled={isLast}
                onClick={() => moveWidget(entry.id, "down")}
              >
                <ArrowDown aria-hidden="true" />
              </Button>
              <Button
                variant="ghost"
                size="icon-xs"
                aria-label="Resize"
                onClick={() => resizeWidget(entry.id, nextSize(entry))}
              >
                <Maximize2 aria-hidden="true" />
              </Button>
              <Button
                variant="ghost"
                size="icon-xs"
                aria-label={entry.pinned ? "Unpin" : "Pin"}
                onClick={() => togglePin(entry.id)}
              >
                {entry.pinned ? <PinOff aria-hidden="true" /> : <Pin aria-hidden="true" />}
              </Button>
              <Button
                variant="ghost"
                size="icon-xs"
                aria-label="Remove"
                disabled={entry.pinned}
                onClick={() => removeWidget(entry.id)}
              >
                <X aria-hidden="true" />
              </Button>
            </div>
          </CardAction>
        </CardHeader>
        <CardContent className="flex-1 overflow-auto text-secondary">
          <contribution.render />
        </CardContent>
      </Card>
    </Reorder.Item>
  );
}
