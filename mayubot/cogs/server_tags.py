from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger(__name__)


class ServerTags(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    tag = app_commands.Group(
        name="tag",
        description="Discord 서버 태그 역할 관리",
        default_permissions=discord.Permissions(manage_roles=True),
    )

    async def _log(self, guild: discord.Guild, text: str, channel_id: int | None) -> None:
        if not channel_id:
            return
        channel = guild.get_channel(channel_id)
        if isinstance(channel, discord.TextChannel):
            try:
                await channel.send(text)
            except discord.HTTPException:
                log.exception("Failed to send tag log in guild %s", guild.id)

    @tag.command(name="setup", description="서버 태그 자동 역할을 생성하고 활성화합니다.")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def setup_tag(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("서버에서만 사용할 수 있습니다.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        cfg = await self.bot.db.get_guild_settings(guild.id)
        role = guild.get_role(cfg.get("tag_role_id")) if cfg.get("tag_role_id") else None
        if role is None:
            try:
                role = await guild.create_role(
                    name="서버 태그 인증", reason="MAYUBOT 서버 태그 자동 역할 설정"
                )
            except discord.Forbidden:
                await interaction.followup.send(
                    "역할 생성 권한이 없습니다. 봇 권한과 역할 순서를 확인하세요.",
                    ephemeral=True,
                )
                return
        await self.bot.db.update_guild_settings(guild.id, tag_enabled=True, tag_role_id=role.id)
        await interaction.followup.send(
            f"서버 태그 자동 역할 활성화 완료: {role.mention}\n태그 변경 이벤트부터 자동 반영합니다.",
            ephemeral=True,
        )

    @tag.command(name="log", description="서버 태그 변경 로그 채널을 설정합니다.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_tag_log(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("서버에서만 사용할 수 있습니다.", ephemeral=True)
            return
        await self.bot.db.update_guild_settings(
            interaction.guild.id, tag_log_channel_id=channel.id
        )
        await interaction.response.send_message(
            f"서버 태그 로그 채널을 {channel.mention}(으)로 설정했습니다.",
            ephemeral=True,
        )

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User) -> None:
        old_tag = getattr(before, "primary_guild", None)
        new_tag = getattr(after, "primary_guild", None)
        if old_tag == new_tag or new_tag is None:
            return
        tag_guild_id = getattr(new_tag, "identity_guild_id", None)
        tag_enabled = getattr(new_tag, "identity_enabled", None)

        for guild in self.bot.guilds:
            cfg = await self.bot.db.get_guild_settings(guild.id)
            if not cfg.get("tag_enabled") or not cfg.get("tag_role_id"):
                continue
            role = guild.get_role(cfg["tag_role_id"])
            member = guild.get_member(after.id)
            if role is None or member is None:
                continue
            has_role = role in member.roles
            should_add = tag_guild_id == guild.id and tag_enabled is True
            should_remove = (
                (tag_guild_id == guild.id and tag_enabled is False)
                or (tag_guild_id is not None and tag_guild_id != guild.id)
            )
            try:
                if should_add and not has_role:
                    await member.add_roles(role, reason="Discord 서버 태그 활성화 감지")
                    await self._log(
                        guild, f"**서버 태그 연결 감지**\n사용자: {member.mention}",
                        cfg.get("tag_log_channel_id"),
                    )
                elif should_remove and has_role:
                    await member.remove_roles(role, reason="Discord 서버 태그 변경 또는 해제 감지")
                    await self._log(
                        guild, f"**서버 태그 해제 감지**\n사용자: {member.mention}",
                        cfg.get("tag_log_channel_id"),
                    )
            except discord.Forbidden:
                log.warning("Cannot sync tag role in guild %s; check role hierarchy.", guild.id)
            except discord.HTTPException:
                log.exception("Tag role sync failed in guild %s", guild.id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ServerTags(bot))
