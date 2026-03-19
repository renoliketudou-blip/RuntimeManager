DEFAULT_IMAGE_REF = (
    "ghcr.io/openclaw/openclaw@sha256:a5a4c83b773aca85a8ba99cf155f09afa33946c0aa5cc6a9ccb6162738b5da02"
)
INIT_PERMISSIONS_IMAGE = "busybox:latest"
PROBE_IMAGE = "busybox:latest"
DEFAULT_NETWORK_NAME = "crewclaw_shared"
DEFAULT_GATEWAY_PORT = 18789
DEFAULT_BRIDGE_PORT = 18790
CONTAINER_GATEWAY_PORT = 18789
CONTAINER_BRIDGE_PORT = 18790
OPENCLAW_HOME_DIR = "/home/node/.openclaw"
OPENCLAW_WORKSPACE_DIR = "/home/node/.openclaw/workspace"
OPENCLAW_CANVAS_DIR = "/home/node/.openclaw/canvas"
OPENCLAW_CRON_DIR = "/home/node/.openclaw/cron"
OPENCLAW_CONFIG_PATH = "/home/node/.openclaw/openclaw.json"
OPENCLAW_SECRET_PATH = "/run/crewclaw/gateway.token"
START_COMMAND = ("node", "dist/index.js", "gateway", "--bind", "lan", "--port", "18789")

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
    "crewclaw.configDir",
    "crewclaw.workspaceDir",
)

