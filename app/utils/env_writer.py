from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_PATH = BASE_DIR / ".env"


def read_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if not ENV_PATH.exists():
        return env
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, _, val = stripped.partition("=")
        env[key.strip()] = val.strip().strip('"').strip("'")
    return env


def write_env(overrides: dict[str, Optional[str]], keep_comments: bool = True) -> None:
    current = ENV_PATH.read_text(encoding="utf-8") if ENV_PATH.exists() else ""
    lines = current.splitlines(keepends=True)
    updated_keys: set[str] = set()

    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            if keep_comments:
                new_lines.append(line)
            continue
        if "=" not in stripped:
            if keep_comments:
                new_lines.append(line)
            continue
        key = stripped.partition("=")[0].strip()
        if key in overrides:
            val = overrides[key]
            if val is not None:
                new_lines.append(f'{key}="{val}"\n')
            else:
                new_lines.append(f'{key}=\n')
            updated_keys.add(key)
        else:
            new_lines.append(line)

    for key, val in overrides.items():
        if key not in updated_keys:
            if val is not None:
                new_lines.append(f'{key}="{val}"\n')
            else:
                new_lines.append(f'{key}=\n')

    ENV_PATH.write_text("".join(new_lines), encoding="utf-8")
