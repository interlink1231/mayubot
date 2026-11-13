from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    discord_token: str
    database_path: Path
    sync_commands: bool
    test_guild_id: int | None

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        token = os.getenv("DISCORD_TOKEN", "").strip()
        if not token:
            raise RuntimeError("DISCORD_TOKEN이 설정되지 않았습니다. .env 파일을 확인하세요.")
        raw_guild_id = os.getenv("TEST_GUILD_ID", "").strip()
        try:
            test_guild_id = int(raw_guild_id) if raw_guild_id else None
        except ValueError as exc:
            raise RuntimeError("TEST_GUILD_ID는 숫자여야 합니다.") from exc
        return cls(
            discord_token=token,
            database_path=Path(os.getenv("DATABASE_PATH", "data/mayubot.sqlite3")),
            sync_commands=os.getenv("SYNC_COMMANDS", "true").lower() in {"1", "true", "yes", "on"},
            test_guild_id=test_guild_id,
        )
