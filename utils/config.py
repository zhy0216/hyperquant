from pathlib import Path

import yaml

REQUIRED_SECTIONS = [
    "exchange", "data", "strategy", "risk", "stop_loss", "notify", "logging"
]


def load_config(path: str) -> dict:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(config_path) as f:
        config = yaml.safe_load(f)

    missing = [s for s in REQUIRED_SECTIONS if s not in config]
    if missing:
        raise KeyError(f"Missing required config sections: {', '.join(missing)}")

    return config
