from __future__ import annotations

from collections import defaultdict, deque
from time import monotonic

import discord
from discord.ext import commands


class AntiRaid(commands.Cog):
    """Detects destructive action bursts and alerts moderators; no automatic admin stripping."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.actions: dict[tuple[int, int], deque[float]] = defaultdict(deque)

    async def _alert(self, guild: discord.Guild, detail: str, actor_id: int) -> None:
        await self.bot.db.add_event(guild.id, "RAID_ALERT", detail, actor_id)
        cfg = await self.bot.db.get_guild_settings(guild.id)
        channel = guild.get_channel(cfg.get("log_channel_id")) if cfg.get("log_channel_id") else None
        if cfg.get("raid_alerts_enabled", 1) and isinstance(channel, discord.TextChannel):
            try:
                await channel.send(
                    f"**서버 테러 의심 활동 감지**\n{detail}\n관리자가 감사 로그를 확인한 뒤 조치해야 합니다."
                )
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_audit_log_entry_create(self, entry: discord.AuditLogEntry) -> None:
        if entry.guild is None or entry.user is None:
            return
        if entry.action not in {
            discord.AuditLogAction.channel_delete,
            discord.AuditLogAction.kick,
            discord.AuditLogAction.ban,
        }:
            return
        guild = entry.guild
        if entry.user.id == guild.owner_id or entry.user.bot:
            return
        key = (guild.id, entry.user.id)
        now = monotonic()
        queue = self.actions[key]
        queue.append(now)
        while queue and now - queue[0] > 12:
            queue.popleft()
        if len(queue) >= 3:
            await self._alert(
                guild,
                f"<@{entry.user.id}> 12초 이내 채널 삭제·추방·차단 감사 로그 {len(queue)}건 감지",
                entry.user.id,
            )
            queue.clear()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AntiRaid(bot))
