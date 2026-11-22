"""사용자 설정(config.json): 마법사가 고른 Orange 와 마지막 호환성 검사 결과."""
from __future__ import annotations

import json
import os
import tempfile
from typing import Any

from . import paths


def load() -> dict[str, Any]:
    try:
        with open(paths.config_file(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(data: dict[str, Any]) -> None:
    """원자적으로 저장(쓰다 죽어도 기존 파일이 깨지지 않게)."""
    d = paths.app_dir()
    d.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(d), prefix="config.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, paths.config_file())
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def update(**kw: Any) -> dict[str, Any]:
    data = load()
    data.update(kw)
    save(data)
    return data
