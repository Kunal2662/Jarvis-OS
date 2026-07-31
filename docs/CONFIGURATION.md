# Configuration

All configuration lives in **`src/jarvis/core/config/settings.py`** and is
loaded from `.env` + environment variables via **pydantic-settings**.

## 1. Precedence

1. Real environment variables  (highest)
2. `.env` file next to the executable / working directory
3. Defaults defined in `Settings` / nested settings classes

## 2. Naming convention

```
JARVIS_<SECTION>_<FIELD>          →   Settings.<section>.<field>
JARVIS_LOG_LEVEL                  →   settings.log.level
JARVIS_OPENAI_API_KEY             →   settings.openai.api_key.get_secret_value()
JARVIS_DB_URL                     →   settings.db.url
```

Section names in the env prefix must match the classes below.

## 3. Sections

| Section       | Class                        | Prefix                   |
|---------------|------------------------------|--------------------------|
| Root          | `Settings`                   | `JARVIS_`                |
| Logging       | `LoggingSettings`            | `JARVIS_LOG_`            |
| FastAPI       | `ApiSettings`                | `JARVIS_API_`            |
| Database      | `DatabaseSettings`           | `JARVIS_DB_`             |
| Vector store  | `VectorStoreSettings`        | `JARVIS_VECTOR_`         |
| OpenAI        | `OpenAISettings`             | `JARVIS_OPENAI_`         |
| Ollama        | `OllamaSettings`             | `JARVIS_OLLAMA_`         |
| STT           | `STTSettings`                | `JARVIS_STT_`            |
| TTS           | `TTSSettings`                | `JARVIS_TTS_`            |
| Browser       | `BrowserSettings`            | `JARVIS_BROWSER_`        |
| Win. autom.   | `WindowsAutomationSettings`  | `JARVIS_WIN_AUTOMATION_` |
| Agent runtime | `AgentSettings`              | `JARVIS_AGENT_`          |
| UI            | `UISettings`                 | `JARVIS_UI_`             |
| Security      | `SecuritySettings`           | `JARVIS_` (flat)         |

## 4. Feature-flag philosophy

Every provider carries an `enabled: bool`. Disabling a provider must never
crash the app — the DI container simply does not build it, and callers
receive a clean `ConfigError` if they try to use it. This lets the same
build ship enabled/disabled providers per user without code changes.

## 5. Validation

`Settings.check()` runs at boot and enforces:

* At least one LLM provider is enabled.
* `llm_default_provider` matches an *enabled* provider.
* `openai.enabled=true` ⇒ `openai.api_key` is non-empty.

Failure raises `ConfigError` — the app exits with a clear message.

## 6. Secrets

* Keys with type `SecretStr` are never printed / logged by default.
* Store the master `JARVIS_SECRET_KEY` (Fernet) in `.env` on dev
  machines; on Windows we recommend the **OS keyring**
  (`JARVIS_USE_OS_KEYRING=true`) so it never touches disk in plaintext.

Generate a fresh key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## 7. Adding a new setting

1. Add the field to the appropriate nested settings class.
2. Add a default that makes the feature **off** by default.
3. Update `.env.example` with a placeholder value.
4. Update this document.
