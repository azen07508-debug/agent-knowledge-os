"""用户记忆：本地 JSON 文件存储的出生档案与咨询历史。

文件位于 data/user_memory.json（data/ 已被 git 忽略）。单进程读写，每次读写都直接
访问文件并原子替换，避免进程内缓存与磁盘不一致。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "user_memory.json"
MAX_HISTORY = 50


class UserMemory:
    """按 user_id 维护出生档案与咨询历史。"""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else DEFAULT_PATH

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)

    @staticmethod
    def _record(data: dict[str, Any], user_id: str) -> dict[str, Any]:
        record = data.setdefault(user_id, {"user_id": user_id})
        record.setdefault("profile", None)
        record.setdefault("history", [])
        return record

    def save_profile(self, user_id: str, profile: dict[str, Any]) -> dict[str, Any]:
        data = self._load()
        self._record(data, user_id)["profile"] = profile
        self._save(data)
        return profile

    def profile(self, user_id: str) -> dict[str, Any] | None:
        record = self._load().get(user_id)
        return record.get("profile") if record else None

    def record(self, user_id: str, entry: dict[str, Any]) -> list[dict[str, Any]]:
        """把一次咨询插到历史最前面，并裁掉超出上限的旧记录。"""
        data = self._load()
        record = self._record(data, user_id)
        record["history"] = [entry, *record["history"]][:MAX_HISTORY]
        self._save(data)
        return record["history"]

    def history(self, user_id: str) -> list[dict[str, Any]]:
        """返回该用户已存的咨询历史（写入时已裁到 MAX_HISTORY）。"""
        record = self._load().get(user_id)
        return record.get("history", []) if record else []
