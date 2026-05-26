from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


DEFAULT_CONFIG = """[llm]
provider = "deepseek"
base_url = "https://api.deepseek.com"
api_key_env = "DEEPSEEK_API_KEY"
model = "deepseek-v4-flash"
temperature = 0.1

[build]
cc = "gcc"
cxx = "g++"
python = "python3"

[supercode]
workdir = ".supercode"
keep_impl = true
"""


@dataclass(slots=True)
class LLMConfig:
    provider: str = "deepseek"
    base_url: str = "https://api.deepseek.com"
    api_key_env: str = "DEEPSEEK_API_KEY"
    model: str = "deepseek-v4-flash"
    temperature: float = 0.1

    @property
    def api_key(self) -> str | None:
        return os.getenv(self.api_key_env)


@dataclass(slots=True)
class BuildConfig:
    cc: str = "gcc"
    cxx: str = "g++"
    python: str = "python3"


@dataclass(slots=True)
class SuperCodeConfig:
    workdir: str = ".supercode"
    keep_impl: bool = True


@dataclass(slots=True)
class Config:
    llm: LLMConfig
    build: BuildConfig
    supercode: SuperCodeConfig
    config_path: Path | None = None


def _deep_update(base: dict, patch: dict) -> dict:
    merged = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_update(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_toml(path: Path) -> dict:
    if not path.exists():
        return {}
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _apply_env(data: dict) -> dict:
    env_map = {
        "SUPERCODE_LLM_PROVIDER": ("llm", "provider"),
        "SUPERCODE_LLM_BASE_URL": ("llm", "base_url"),
        "SUPERCODE_LLM_API_KEY_ENV": ("llm", "api_key_env"),
        "SUPERCODE_LLM_MODEL": ("llm", "model"),
        "SUPERCODE_BUILD_CC": ("build", "cc"),
        "SUPERCODE_BUILD_CXX": ("build", "cxx"),
        "SUPERCODE_BUILD_PYTHON": ("build", "python"),
        "SUPERCODE_WORKDIR": ("supercode", "workdir"),
    }
    merged = dict(data)
    for env_key, (section, key) in env_map.items():
        value = os.getenv(env_key)
        if value is None:
            continue
        section_data = dict(merged.get(section, {}))
        section_data[key] = value
        merged[section] = section_data
    return merged


def load_config(cwd: Path | None = None) -> Config:
    cwd = cwd or Path.cwd()
    local_path = cwd / "supercode.toml"
    home_path = Path.home() / ".config" / "supercode" / "config.toml"

    data: dict = tomllib.loads(DEFAULT_CONFIG)
    config_path = None
    if home_path.exists():
        data = _deep_update(data, _load_toml(home_path))
        config_path = home_path
    if local_path.exists():
        data = _deep_update(data, _load_toml(local_path))
        config_path = local_path
    data = _apply_env(data)

    llm_data = data.get("llm", {})
    build_data = data.get("build", {})
    supercode_data = data.get("supercode", {})
    return Config(
        llm=LLMConfig(
            provider=llm_data.get("provider", "deepseek"),
            base_url=llm_data.get("base_url", "https://api.deepseek.com"),
            api_key_env=llm_data.get("api_key_env", "DEEPSEEK_API_KEY"),
            model=llm_data.get("model", "deepseek-v4-flash"),
            temperature=float(llm_data.get("temperature", 0.1)),
        ),
        build=BuildConfig(
            cc=build_data.get("cc", "gcc"),
            cxx=build_data.get("cxx", "g++"),
            python=build_data.get("python", "python3"),
        ),
        supercode=SuperCodeConfig(
            workdir=supercode_data.get("workdir", ".supercode"),
            keep_impl=bool(supercode_data.get("keep_impl", True)),
        ),
        config_path=config_path,
    )


def init_config(destination: Path | None = None) -> Path:
    destination = destination or (Path.cwd() / "supercode.toml")
    if destination.exists():
        raise FileExistsError(f"config already exists: {destination}")
    destination.write_text(DEFAULT_CONFIG, encoding="utf-8")
    return destination
