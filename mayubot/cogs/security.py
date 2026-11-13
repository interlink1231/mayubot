from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


class Security(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    security = app_commands.Group(
        name="security",
        description="MAYUBOT 서버 보안 관리",
        default_permissions=discord.Permissions(manage_guild=True),
    )

    @security.command(name="setup", description="이 서버의 기본 보안 설정을 초기화합니다.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_security(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("서버에서만 사용할 수 있습니다.", ephemeral=True)
            return
        await self.bot.db.ensure_guild(interaction.guild.id)
        await interaction.response.send_message(
            "기본 보안 설정이 준비되었습니다. 초대 링크·도배·멘션 검열은 기본 활성화 상태입니다.",
            ephemeral=True,
        )

    @security.command(name="log", description="보안 이벤트 로그 채널을 설정합니다.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_log(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("서버에서만 사용할 수 있습니다.", ephemeral=True)
            return
        await self.bot.db.update_guild_settings(
            interaction.guild.id, log_channel_id=channel.id
        )
        await interaction.response.send_message(
            f"보안 로그 채널을 {channel.mention}(으)로 설정했습니다.",
            ephemeral=True,
        )

    @security.command(name="status", description="현재 서버의 보안 설정을 확인합니다.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def status(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("서버에서만 사용할 수 있습니다.", ephemeral=True)
            return
        cfg = await self.bot.db.get_guild_settings(interaction.guild.id)
        embed = discord.Embed(title="MAYUBOT 보안 상태", color=discord.Color.dark_teal())
        for label, key in (
            ("자동 검열", "automod_enabled"), ("초대 링크", "invite_filter"),
            ("도배·단타", "spam_filter"), ("과도한 멘션", "mention_filter"),
            ("테러 감지 알림", "raid_alerts_enabled"), ("서버 태그", "tag_enabled"),
        ):
            embed.add_field(
                name=label,
                value="활성화" if cfg.get(key) else "비활성화",
                inline=True,
            )
        channel_id = cfg.get("log_channel_id")
        embed.add_field(
            name="보안 로그 채널",
            value=f"<#{channel_id}>" if channel_id else "미설정",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @security.command(name="scan", description="서버 구성원을 MAYUBOT 검토 목록과 대조합니다.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def scan(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("서버에서만 사용할 수 있습니다.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        members = [member async for member in guild.fetch_members(limit=None)]
        entries = await self.bot.db.find_blacklisted_members([member.id for member in members])
        if not entries:
            await interaction.followup.send(
                f"검사 완료: 구성원 {len(members)}명 중 일치 계정이 없습니다.",
                ephemeral=True,
            )
            return
        lines = [
            f"• <@{entry['user_id']}> — 코드: {entry['reason_code']}"
            for entry in entries[:20]
        ]
        embed = discord.Embed(
            title="악성유저 검토 목록 일치 결과",
            description="\n".join(lines),
            color=discord.Color.orange(),
        )
        embed.set_footer(
            text=f"총 {len(entries)}건 · 참고 결과이며 자동 제재는 수행하지 않았습니다."
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Security(bot))
