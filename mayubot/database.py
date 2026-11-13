from __future__ import annotations

from pathlib import Path
from typing import Any

import aiosqlite


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    async def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA foreign_keys=ON;
                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id INTEGER PRIMARY KEY,
                    log_channel_id INTEGER,
                    automod_enabled INTEGER NOT NULL DEFAULT 1,
                    invite_filter INTEGER NOT NULL DEFAULT 1,
                    spam_filter INTEGER NOT NULL DEFAULT 1,
                    mention_filter INTEGER NOT NULL DEFAULT 1,
                    raid_alerts_enabled INTEGER NOT NULL DEFAULT 1,
                    tag_enabled INTEGER NOT NULL DEFAULT 0,
                    tag_role_id INTEGER,
                    tag_log_channel_id INTEGER,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS whitelist (
                    guild_id INTEGER NOT NULL,
                    target_id INTEGER NOT NULL,
                    target_type TEXT NOT NULL CHECK(target_type IN ('member','role','channel')),
                    added_by INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (guild_id, target_id, target_type)
                );
                CREATE TABLE IF NOT EXISTS blacklist (
                    user_id INTEGER PRIMARY KEY,
                    status TEXT NOT NULL DEFAULT 'reviewed'
                        CHECK(status IN ('pending','reviewed','rejected','appealed')),
                    reason_code TEXT NOT NULL,
                    evidence_reference TEXT,
                    added_by INTEGER NOT NULL,
                    reviewed_by INTEGER,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS guild_blacklist (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK(status IN ('pending','reviewed','rejected')),
                    reason_code TEXT NOT NULL,
                    evidence_reference TEXT,
                    added_by INTEGER NOT NULL,
                    reviewed_by INTEGER,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (guild_id, user_id)
                );
                CREATE INDEX IF NOT EXISTS idx_guild_blacklist_status
                    ON guild_blacklist(guild_id, status);

                CREATE TABLE IF NOT EXISTS security_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER,
                    event_type TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_security_events_guild_time
                    ON security_events(guild_id, created_at);
                """
            )
            await db.commit()

    async def ensure_guild(self, guild_id: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)", (guild_id,)
            )
            await db.commit()

    async def get_guild_settings(self, guild_id: int) -> dict[str, Any]:
        await self.ensure_guild(guild_id)
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,)
            )
            row = await cur.fetchone()
            return dict(row) if row else {}

    async def update_guild_settings(self, guild_id: int, **values: Any) -> None:
        allowed = {
            "log_channel_id", "automod_enabled", "invite_filter", "spam_filter",
            "mention_filter", "raid_alerts_enabled", "tag_enabled",
            "tag_role_id", "tag_log_channel_id",
        }
        updates = {k: v for k, v in values.items() if k in allowed}
        if not updates:
            return
        await self.ensure_guild(guild_id)
        columns = ", ".join(f"{key} = ?" for key in updates)
        params = [int(v) if isinstance(v, bool) else v for v in updates.values()]
        params.append(guild_id)
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                f"UPDATE guild_settings SET {columns}, updated_at = CURRENT_TIMESTAMP WHERE guild_id = ?",
                params,
            )
            await db.commit()

    async def is_whitelisted(
        self, guild_id: int, member_id: int, role_ids: list[int], channel_id: int
    ) -> bool:
        targets = [(member_id, "member"), (channel_id, "channel")]
        targets.extend((role_id, "role") for role_id in role_ids)
        async with aiosqlite.connect(self.path) as db:
            for target_id, target_type in targets:
                cur = await db.execute(
                    """SELECT 1 FROM whitelist
                    WHERE guild_id = ? AND target_id = ? AND target_type = ? LIMIT 1""",
                    (guild_id, target_id, target_type),
                )
                if await cur.fetchone():
                    return True
        return False

    async def add_event(
        self, guild_id: int, event_type: str, detail: str, user_id: int | None = None
    ) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """INSERT INTO security_events (guild_id, user_id, event_type, detail)
                VALUES (?, ?, ?, ?)""",
                (guild_id, user_id, event_type, detail[:1000]),
            )
            await db.commit()

    async def add_blacklist_entry(
        self, guild_id: int, user_id: int, reason_code: str,
        evidence_reference: str | None, added_by: int,
    ) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                """INSERT OR IGNORE INTO guild_blacklist
                (guild_id, user_id, reason_code, evidence_reference, added_by)
                VALUES (?, ?, ?, ?, ?)""",
                (guild_id, user_id, reason_code[:80], evidence_reference, added_by),
            )
            await db.commit()
            return cur.rowcount > 0

    async def review_blacklist_entry(
        self, guild_id: int, user_id: int, status: str, reviewed_by: int
    ) -> bool:
        if status not in {"reviewed", "rejected"}:
            raise ValueError("Invalid review status")
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                """UPDATE guild_blacklist
                SET status = ?, reviewed_by = ?, updated_at = CURRENT_TIMESTAMP
                WHERE guild_id = ? AND user_id = ? AND status = 'pending'""",
                (status, reviewed_by, guild_id, user_id),
            )
            await db.commit()
            return cur.rowcount > 0

    async def remove_blacklist_entry(self, guild_id: int, user_id: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "DELETE FROM guild_blacklist WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
            await db.commit()
            return cur.rowcount > 0

    async def list_blacklist_entries(
        self, guild_id: int, status: str | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            if status:
                cur = await db.execute(
                    """SELECT user_id, status, reason_code, evidence_reference,
                    added_by, reviewed_by, created_at
                    FROM guild_blacklist WHERE guild_id = ? AND status = ?
                    ORDER BY created_at DESC LIMIT ?""",
                    (guild_id, status, limit),
                )
            else:
                cur = await db.execute(
                    """SELECT user_id, status, reason_code, evidence_reference,
                    added_by, reviewed_by, created_at
                    FROM guild_blacklist WHERE guild_id = ?
                    ORDER BY created_at DESC LIMIT ?""",
                    (guild_id, limit),
                )
            return [dict(row) for row in await cur.fetchall()]

    async def find_blacklisted_members(
        self, guild_id: int, member_ids: list[int]
    ) -> list[dict[str, Any]]:
        if not member_ids:
            return []
        marks = ",".join("?" for _ in member_ids)
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                f"""SELECT user_id, reason_code, status, evidence_reference
                FROM guild_blacklist
                WHERE guild_id = ? AND status = 'reviewed' AND user_id IN ({marks})""",
                [guild_id, *member_ids],
            )
            return [dict(row) for row in await cur.fetchall()]
