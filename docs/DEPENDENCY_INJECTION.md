# Dependency Injection

We use [`dependency-injector`](https://python-dependency-injector.ets-labs.org/)
because it plays well with both PySide6 (sync UI code) and FastAPI /
`asyncio` (server code), supports lazy factories out of the box, and lets us
wire packages instead of tagging every function.

## 1. The container

`src/jarvis/core/di/container.py` declares **the** container. It is the
single composition root; no other module builds adapters or services.

```python
from jarvis.core.di.container import Container

container = Container()
container.config.from_pydantic(settings)
container.wire(packages=["jarvis.services", "jarvis.features", "jarvis.ui", ...])
```

## 2. Provider kinds we use

| Kind         | When                                                              |
|--------------|-------------------------------------------------------------------|
| `Singleton`  | Adapters and cross-cutting objects (`event_bus`, `llm_provider`). |
| `Factory`    | Application services and short-lived objects.                     |
| `Configuration` | Access to raw settings values inside the container itself.     |

## 3. Rules

1. **Never** import the container inside a service, agent, feature or
   widget — receive dependencies via the constructor.
2. Adapter construction is *lazy* — factories inside the container import
   the concrete class only when the singleton is first requested. This
   keeps import time low and lets us skip Windows-only imports on Linux.
   See §6 for exactly which providers this applies to and why.
3. Provider names in the container **must** match the field names services
   ask for (see the `providers.Factory` declarations).

## 4. Wiring FastAPI endpoints

Endpoints declare a dependency using the standard `Depends(Provide[...])`
pattern from `dependency-injector.wiring`, so no request touches the raw
container:

```python
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from jarvis.core.di.container import Container
from jarvis.services.chat_service import ChatService

router = APIRouter()

@router.post("/chat")
@inject
async def chat(
    prompt: str,
    service: ChatService = Depends(Provide[Container.chat_service]),
) -> dict:
    return {"answer": await service.ask(prompt)}
```

## 5. Testing

Override providers per test:

```python
from jarvis.core.di.container import Container

def test_chat(mock_llm):
    container = Container()
    container.llm_provider.override(mock_llm)
    service = container.chat_service()
    ...
    container.unwire()
```

## 6. Two provider forms, and why they behave differently

`dependency-injector` supports two ways to tell a provider what to build.
They look similar but have opposite import timing, which matters for
startup performance:

```python
# String-path form: dependency-injector imports the target class the
# moment this line runs -- i.e. at Container CLASS DECLARATION time,
# when `container.py` is first imported. This is NOT lazy, despite
# looking like it defers construction.
theme_service = providers.Singleton(
    "jarvis.services.theme_service.ThemeService", settings=settings,
)

# Callable form: the import lives inside the function body, so it only
# runs the first time the provider is *resolved* (`container.x()`), not
# at import time. This is genuinely lazy.
def _build_agent_orchestrator(*, settings, llm, ...):
    from jarvis.agents.orchestrator import AgentOrchestrator
    return AgentOrchestrator(settings=settings, llm=llm, ...)

agent_orchestrator = providers.Singleton(_build_agent_orchestrator, settings=settings, ...)
```

**Root cause of a real bug (found 2026-07, fixed 2026-08):** the container
docstring always claimed importing it was "cheap and side-effect-free," but
most application services were registered with the string-path form, which
eagerly imports its target at class-declaration time. `agent_orchestrator`
in particular pulled in `jarvis.agents.graph` → LangGraph/LangChain/LangSmith
this way, adding roughly 1.6s to every `import jarvis.core.di.container`,
whether or not the agent was ever used in that process.

**Which providers are lazy today:** the 14 infrastructure adapters
(`llm_provider`, `stt_provider`, ..., `os_automation`) plus four
application-layer providers confirmed (by measuring, not guessing) to pull
in something heavy or conditionally-used: `conversation_service`,
`memory_service`, `automation_service`, and `agent_orchestrator`. Every
other service is still registered with the string-path form — measured at
within ~0.1s of the shared `Settings`+logger import floor that the
container pays regardless, so converting them would add boilerplate with
no measurable benefit. **Before registering a new service, measure its
cold-import cost** (see `agent_trace`/stabilization tooling, or just
`python -c "import time; t=time.perf_counter(); import <module>;
print(time.perf_counter()-t)"` from `src/`) rather than assuming the
callable form is always required.

**Effect of the fix:** `import jarvis.core.di.container` dropped from
~2.9s to ~1.6s (measured, same machine, back-to-back runs), and RSS at a
lightweight-service checkpoint dropped from ~101MB to ~55MB. Resolving
`agent_orchestrator` for the first time still costs about the same as
before (~5.4s, dominated by the same LangGraph/LangChain/LangSmith import
plus graph compilation) — that cost didn't disappear, it correctly moved
to the first actual agent/chat use instead of being paid unconditionally
at every process start, matching how `main_window.py`/`app.py` already use
it (never resolved during boot; `agent_orchestrator()` is only called from
a deferred shutdown-hook closure and the Agent Trace developer view).
