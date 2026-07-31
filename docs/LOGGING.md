# Logging

## Stack

* **loguru** — pretty console, rotating file sink, JSON sink.
* **structlog** — reserved for adding structured contexts (bound loggers).
* Stdlib `logging` is intercepted so libraries end up in the same pipeline.

Bootstrapped by `jarvis.core.logging.logger.configure_logging(settings)`.

## Levels

| Level      | Use                                                      |
|------------|----------------------------------------------------------|
| `TRACE`    | Extremely verbose (only when debugging protocols).       |
| `DEBUG`    | Developer info — never for end-user output.              |
| `INFO`     | Milestones (app started, provider ready, task complete). |
| `WARNING`  | Recoverable oddities (retry, fallback).                  |
| `ERROR`    | Failed operations that the app still recovers from.      |
| `CRITICAL` | The app is about to crash / restart.                     |

## Sinks

| Sink       | When enabled                              | Format                    |
|------------|-------------------------------------------|---------------------------|
| Console    | Always                                    | Coloured (dev) / JSON (prod) |
| File       | `JARVIS_LOG_FILE_ENABLED=true` (default)  | Non-coloured, grep-friendly, rotated by `JARVIS_LOG_FILE_ROTATION` and retained per `JARVIS_LOG_FILE_RETENTION`. |

Log file path: `<data_dir>/logs/jarvis.log`.

## Usage

```python
from jarvis.core.logging.logger import get_logger

log = get_logger(__name__)

log.info("Loaded {} providers.", n)
log.bind(request_id=req.id, user=req.user).info("Received request.")
try:
    ...
except SomeError:
    log.exception("Failed to talk to provider.")
```

## What NOT to do

* Don't call `logging.getLogger(...)` — always `get_logger`.
* Don't `print()`.
* Don't log secrets. `SecretStr` fields render as `**********` — do not
  call `.get_secret_value()` inside a log message.

## Log correlation

Feature milestones will introduce a `request_id`/`thread_id` context via
`structlog.contextvars` so every log line for a given agent invocation
shares an id — grep-friendly across sinks.
