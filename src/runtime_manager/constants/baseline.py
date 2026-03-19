DEFAULT_IMAGE_REF = (
    "ghcr.io/openclaw/openclaw@sha256:a5a4c83b773aca85a8ba99cf155f09afa33946c0aa5cc6a9ccb6162738b5da02"
)
DEFAULT_NETWORK_NAME = "crewclaw_shared"
DEFAULT_GATEWAY_PORT = 18789
DEFAULT_BRIDGE_PORT = 18790

REQUIRED_ENV_KEYS = (
    "HOME",
    "TERM",
    "TZ",
    "OPENAI_BASE_URL",
)

OPTIONAL_ENV_KEYS = (
    "OPENCLAW_GATEWAY_TOKEN",
    "OPENCLAW_ALLOW_INSECURE_PRIVATE_WS",
    "CLAUDE_AI_SESSION_KEY",
    "CLAUDE_WEB_SESSION_KEY",
    "CLAUDE_WEB_COOKIE",
)

LABEL_KEYS = (
    "crewclaw.managed",
    "crewclaw.userId",
    "crewclaw.runtimeId",
    "crewclaw.volumeId",
    "crewclaw.routeHost",
    "crewclaw.retentionPolicy",
)

