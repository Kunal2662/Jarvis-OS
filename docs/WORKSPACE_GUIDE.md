# Workspace Guide

How the 9 full desktop workspaces (Voice, Files & Drive, Browser,
Coding, Finance, Smart Home, Calendar, Gmail, Spotify) are built, and
how to add a new one or extend an existing one.

## Anatomy

Every workspace lives in `ui/views/workspaces/<name>_workspace.py` and
is built exclusively from the shared scaffold in
`ui/components/workspace.py` plus the rest of the component library —
no workspace hand-rolls its own header, card, or list styling:

| Piece            | Component                                          |
|-------------------|-----------------------------------------------------|
| Title + status + search + toolbar | `WorkspaceHeader`                     |
| Stat tiles         | `CardGrid` + `StatTile`                             |
| Section content    | `SectionCard`                                       |
| Tables             | `SimpleTable` (small/simple) or `VirtualTable` (large/scaling) |
| Lists              | `SimpleListPanel`                                   |
| Charts             | `MiniBarChart` / `MiniLineChart` (`ui/components/charts.py`) |
| Recent activity    | `ActivityFeed`                                      |
| Quick actions      | `QuickActionsRow`                                   |
| Loading/empty/error| `WorkspaceStateStack` (`LoadingState`/`EmptyState`/`ErrorState`) |
| Outer scroll container | `ScrollableColumn`                              |

## Data

Workspaces render **mock data only** — no real Gmail/Spotify/Finance/
Smart-Home/etc. API calls happen from a workspace. The five that mirror
a Home-dashboard service card (Gmail, Spotify, Finance, Smart Home)
pull from the same `Mock*Provider` classes in
`features/integrations/mocks.py` that back the `ServiceWidget` cards,
so the full-screen workspace and the dashboard card never show
contradictory data. See `FUTURE_INTEGRATION_GUIDE.md` for how a real
integration replaces a mock provider later.

## Adding a new workspace

1. Create `ui/views/workspaces/<name>_workspace.py`; build it from the
   table above.
2. Export it from `ui/views/workspaces/__init__.py`.
3. In `ui/main_window.py`, add the nav id to `_WORKSPACE_FACTORIES`
   (and to `_REAL_PAGES` if it should count as a "real" page for the
   `_on_nav_selected` gating logic). Workspaces are built **lazily** —
   on first navigation to that nav id, not at app startup — so nothing
   else needs to change for the lazy-loading behavior to apply.
4. If the nav item doesn't exist yet in the sidebar, add it to
   `NAV_ITEMS` in `ui/widgets/sidebar.py` and register an icon key in
   `ui/components/icons.py`'s `_EMOJI_DEFAULTS`.

## Performance

* Workspaces are constructed on first visit, not eagerly — see
  `MainWindow._on_nav_selected`.
* Any table that could realistically grow into the hundreds/thousands
  of rows (a real inbox, a real file listing) should use `VirtualTable`
  (`ui/components/virtual_list.py`, a `QTableView` + `QAbstractTableModel`)
  instead of `SimpleTable` (`QTableWidget`, which materializes a
  `QTableWidgetItem` per cell up front). The Gmail workspace's inbox is
  the reference example.
* Any widget that kicks off an async refresh from its own constructor
  must go through `ui/async_utils.py`'s `fire_and_forget()`, not a raw
  `asyncio.ensure_future()` — see that module's docstring for why.
