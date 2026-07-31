# Future Integration Guide

How to replace any of the Milestone 5 mock service integrations
(Gmail, Spotify, Weather, Finance, Smart Home) — or the Plugin/
Transcript/Update providers — with a real backend, without touching UI
code.

## The pattern

Every unfinished integration has:

1. **A port** in `core/interfaces/providers.py` — `IGmailProvider`,
   `ISpotifyProvider`, `IWeatherProvider`, `IFinanceProvider`,
   `ISmartHomeProvider`, `IPluginProvider`, `ITranscriptProvider`,
   `IUpdateProvider`. All async, all `Protocol`-based like every other
   port in this codebase (`core/interfaces/*.py`).
2. **A mock adapter** implementing that port —
   `features/integrations/mocks.py` (`MockGmailProvider`,
   `MockSpotifyProvider`, `MockWeatherProvider`, `MockFinanceProvider`,
   `MockSmartHomeProvider`) and `features/plugins/mock_provider.py`
   (`MockPluginProvider`).
3. **UI code that only ever depends on the port**, never the mock
   class directly:
   * `ui/components/service_widget.py`'s `ServiceWidget` takes an
     `on_refresh: Callable[[], Awaitable[dict]]` closure — see
     `home_view.py`'s `_build_service_row` for how each card's closure
     currently calls a `Mock*Provider` and could just as easily call a
     real one.
   * The Gmail/Spotify/Finance/Smart-Home workspaces
     (`ui/views/workspaces/`) take an optional `provider` constructor
     argument that defaults to the mock, e.g.
     `GmailWorkspace(provider: MockGmailProvider | None = None)`.
   * `plugin_manager_view.py` only calls methods on
     `self._provider: IPluginProvider`.

## Adding a real provider

1. Implement the interface, e.g.
   `infrastructure/gmail/real_gmail_provider.py: RealGmailProvider(IGmailProvider)`,
   using whatever real API/SDK is appropriate (Gmail API, Spotify Web
   API, a weather API, a brokerage API, a smart-home hub SDK).
2. Wire it into `core/di/container.py` as a new provider, gated by a
   settings flag (e.g. `settings.integrations.gmail_enabled`) so the
   mock remains the default until credentials are configured — follow
   the same pattern `container.py` already uses for `llm_provider`,
   `stt_provider`, etc.
3. Pass the real instance into `ServiceWidget`'s `on_refresh` closure
   and into the matching workspace's `provider=` argument. No changes
   are needed inside `ServiceWidget`, the workspace views, or any
   component in `ui/components/` — that's the entire point of coding
   against the interface.
4. Update the "What's real vs. mock" table in
   `MILESTONE_5_DELIVERY.md` for that integration.

## Anti-patterns

* Importing a `Mock*Provider` from inside a shared component
  (`ServiceWidget`, `WorkspaceHeader`, etc.) — those must stay
  provider-agnostic.
* Skipping the interface and wiring a concrete SDK client straight into
  a view — breaks the "swap without UI changes" guarantee this whole
  pattern exists for.
* Making network calls from a `ui/` module directly — real integrations
  belong in `infrastructure/`, called through a `features/` or
  `services/` layer, exactly like every other adapter in this codebase
  (see `docs/ARCHITECTURE.md`).
