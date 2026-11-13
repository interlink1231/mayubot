from __future__ import annotations

import re
from collections import defaultdict, deque
from datetime import timedelta
from time import monotonic

import discord
from discord.ext import commands

INVITE_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:discord\.gg|discord(?:app)?\.com/invite)/[A-Za-z0-9-]+",
    re.IGNORECASE,
)


class AutoModeration(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.recent: dict[tuple[int, int], deque[tuple[float, str]]] = defaultdict(deque)

    async def _log(self, guild: discord.Guild, text: str, user_id: int) -> None:
        await self.bot.db.add_event(guild.id, "AUTOMOD", text, user_id)
        cfg = await self.bot.db.get_guild_settings(guild.id)
        channel = guild.get_channel(cfg.get("log_channel_id")) if cfg.get("log_channel_id") else None
        if isinstance(channel, discord.TextChannel):
            try:
                await channel.send(text[:1900])
            except discord.HTTPException:
                pass

    async def _exempt(self, message: discord.Message) -> bool:
        member = message.author
        if not isinstance(member, discord.Member):
            return True
        if member.id == message.guild.owner_id or member.guild_permissions.administrator:
            return True
        return await self.bot.db.is_whitelisted(
            message.guild.id, member.id, [r.id for r in member.roles], message.channel.id
        )

    async def _punish(self, message: discord.Message, reason: str) -> None:
        member = message.author
        if not isinstance(member, discord.Member):
            return
        try:
            await message.delete()
        except discord.HTTPException:
            pass
        try:
            await member.timeout(timedelta(minutes=5), reason=f"MAYUBOT 자동 검열: {reason}")
            result = f"{member.mention} 자동 검열: {reason} (타임아웃 5분)"
        except (discord.Forbidden, discord.HTTPException):
            result = f"{member.mention} 자동 검열 감지: {reason}. 타임아웃은 권한 또는 역할 순서 문제로 적용하지 못했습니다."
        await self._log(message.guild, result, member.id)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        if await self._exempt(message):
            return
        cfg = await self.bot.db.get_guild_settings(message.guild.id)
        if not cfg.get("automod_enabled", 1):
            return
        if cfg.get("invite_filter", 1) and INVITE_RE.search(message.content):
            await self._punish(message, "타 서버 초대 링크 전송")
            return
        if cfg.get("mention_filter", 1) and (
            message.mention_everyone or len(message.mentions) >= 8
        ):
            await self._punish(message, "과도한 멘션")
            return
        if cfg.get("spam_filter", 1):
            key = (message.guild.id, message.author.id)
            now = monotonic()
            queue = self.recent[key]
            queue.append((now, message.content[:300]))
            while queue and now - queue[0][0] > 8:
                queue.popleft()
            repeats = sum(1 for _, text in queue if text == message.content[:300])
            if len(queue) >= 6 or repeats >= 3:
                await self._punish(message, "짧은 시간 내 반복 메시지 또는 도배")
                queue.clear()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AutoModeration(bot))
