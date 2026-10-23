"""docker-compose chỉ chuyển tiếp biến đã khai báo: mọi biến cấu hình của từng tiến trình phải tới được service tương ứng.

Không cần Docker: đọc docker-compose.yml dạng text (mỗi service có khối `environment:` KEY: value).
"""
import re
from pathlib import Path

import pytest

from app.settings.api import ApiSettings
from app.settings.mcp import McpSettings
from app.settings.migrate import MigrateSettings

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE = REPO_ROOT / "docker-compose.yml"
ENV_EXAMPLE = REPO_ROOT / ".env.example"

# Biến mà compose cố ý đặt cứng/ghép cho từng service (không đọc từ .env của operator)
_FIXED_BY_COMPOSE = {
    "api": {"database_url", "mcp_server_url"},
    "mcp-server": {"database_url", "mcp_host", "mcp_port"},
    # BOOTSTRAP_DATABASE_URL được ghép từ POSTGRES_*; migrate không đọc log_level (bootstrap ghi log mức INFO)
    "migrate": {"log_level"},
}


def _service_environments() -> dict[str, dict[str, str]]:
    services: dict[str, dict[str, str]] = {}
    current: str | None = None
    in_env = False
    in_services = False
    for line in COMPOSE.read_text(encoding="utf-8").splitlines():
        if re.match(r"^services:\s*$", line):
            in_services = True
            continue
        if in_services and re.match(r"^\S", line):
            in_services = False
        if not in_services:
            continue
        if m := re.match(r"^  ([\w-]+):\s*$", line):
            current, in_env = m.group(1), False
            services[current] = {}
        elif re.match(r"^    environment:\s*$", line):
            in_env = True
        elif re.match(r"^    \S", line):
            in_env = False
        elif in_env and current and (m := re.match(r"^      ([A-Z][A-Z0-9_]*):\s*(.*?)\s*$", line)):
            services[current][m.group(1)] = m.group(2)
    return services


@pytest.mark.parametrize(
    ("service", "settings_cls"),
    [("api", ApiSettings), ("mcp-server", McpSettings), ("migrate", MigrateSettings)],
)
def test_every_setting_reaches_its_service(service, settings_cls):
    env = _service_environments()[service]
    expected = {name.upper() for name in settings_cls.model_fields} - {n.upper() for n in _FIXED_BY_COMPOSE[service]}
    missing = sorted(expected - env.keys())
    assert not missing, f"service {service} không nhận biến {missing}: sửa docker-compose.yml"


def test_forwarded_knobs_have_defaults_and_follow_dot_env():
    envs = _service_environments()
    for service, names in {
        "api": ("DB_POOL_MAX", "SA_POOL_SIZE", "SA_MAX_OVERFLOW", "LANGGRAPH_POOL_MAX", "LLM_TEMPERATURE", "LLM_TIMEOUT_S"),
        "mcp-server": ("DB_POOL_MAX",),
    }.items():
        for name in names:
            assert re.fullmatch(rf"\$\{{{name}:-[^}}]+\}}", envs[service][name]), f"{service}.{name} = {envs[service][name]}"


def test_seed_demo_data_is_off_in_compose_by_default():
    assert _service_environments()["migrate"]["SEED_DEMO_DATA"] == "${SEED_DEMO_DATA:-false}"


def test_documented_env_vars_are_consumed_by_some_service():
    """Mỗi biến trong .env.example (kể cả dòng comment `# NAME=`) phải được compose dùng, trừ biến chỉ dùng khi chạy tay."""
    documented = set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", ENV_EXAMPLE.read_text(encoding="utf-8"), re.MULTILINE))
    compose_text = COMPOSE.read_text(encoding="utf-8")
    manual_only = {"BOOTSTRAP_DATABASE_URL", "DATABASE_URL"}
    unused = sorted(n for n in documented - manual_only if "${" + n not in compose_text)
    assert not unused, f"biến có trong .env.example nhưng compose không chuyển tiếp: {unused}"
