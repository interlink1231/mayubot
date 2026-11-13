from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


class Blacklist(commands.Cog):
    """Guild-local, moderator-reviewed account reference list."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    blacklist = app_commands.Group(
        name="blacklist",
        description="서버별 악성 계정 검토 목록 관리",
        default_permissions=discord.Permissions(manage_guild=True),
    )

    @blacklist.command(name="add", description="검토 대기 계정을 등록합니다.")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(
        user="검토할 Discord 계정",
        reason_code="사유 분류 코드 (예: RAID, SPAM, SCAM)",
        evidence="증거 링크 또는 내부 기록 식별자",
    )
    async def add(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        reason_code: app_commands.Range[str, 2, 80],
        evidence: app_commands.Range[str, 1, 300] | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("서버에서만 사용할 수 있습니다.", ephemeral=True)
            return
        created = await self.bot.db.add_blacklist_entry(
            interaction.guild.id, user.id, reason_code, evidence, interaction.user.id
        )
        if not created:
            await interaction.response.send_message(
                "이미 이 서버의 검토 목록에 등록된 계정입니다.", ephemeral=True
            )
            return
        await self.bot.db.add_event(
            interaction.guild.id, "BLACKLIST_PENDING",
            f"검토 대기 등록: user_id={user.id}, reason={reason_code}",
            interaction.user.id,
        )
        await interaction.response.send_message(
            f"{user.mention} 계정을 검토 대기 목록에 등록했습니다.\n"
            "관리자 검토 전까지 security scan 결과에는 포함되지 않습니다.",
            ephemeral=True,
        )

    @blacklist.command(name="review", description="검토 대기 계정을 승인하거나 반려합니다.")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(user="검토할 계정", approve="승인 여부")
    async def review(
        self, interaction: discord.Interaction, user: discord.User, approve: bool
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("서버에서만 사용할 수 있습니다.", ephemeral=True)
            return
        status = "reviewed" if approve else "rejected"
        changed = await self.bot.db.review_blacklist_entry(
            interaction.guild.id, user.id, status, interaction.user.id
        )
        if not changed:
            await interaction.response.send_message(
                "검토 대기 상태인 항목을 찾지 못했습니다.", ephemeral=True
            )
            return
        await self.bot.db.add_event(
            interaction.guild.id, "BLACKLIST_REVIEW",
            f"검토 결과: user_id={user.id}, status={status}",
            interaction.user.id,
        )
        result = "승인" if approve else "반려"
        await interaction.response.send_message(
            f"{user.mention} 계정 검토를 {result}했습니다.", ephemeral=True
        )

    @blacklist.command(name="list", description="서버별 검토 목록을 확인합니다.")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.choices(status=[
        app_commands.Choice(name="검토 대기", value="pending"),
        app_commands.Choice(name="승인", value="reviewed"),
        app_commands.Choice(name="반려", value="rejected"),
        app_commands.Choice(name="전체", value="all"),
    ])
    async def list_entries(
        self,
        interaction: discord.Interaction,
        status: app_commands.Choice[str] | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("서버에서만 사용할 수 있습니다.", ephemeral=True)
            return
        selected = status.value if status and status.value != "all" else None
        entries = await self.bot.db.list_blacklist_entries(
            interaction.guild.id, selected, limit=20
        )
        if not entries:
            await interaction.response.send_message(
                "해당 목록에 등록된 계정이 없습니다.", ephemeral=True
            )
            return
        lines = []
        for entry in entries:
            evidence = entry["evidence_reference"] or "증거 참조 없음"
            lines.append(
                f"<@{entry['user_id']}> · {entry['status']} · "
                f"{entry['reason_code']}\n증거: {evidence[:120]}"
            )
        embed = discord.Embed(
            title="서버 악성 계정 검토 목록",
            description="\n\n".join(lines)[:4000],
            color=discord.Color.dark_teal(),
        )
        embed.set_footer(text="서버별 목록 · 최근 최대 20건 · 관리자 전용")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @blacklist.command(name="remove", description="서버의 검토 목록에서 계정을 삭제합니다.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def remove(
        self, interaction: discord.Interaction, user: discord.User
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("서버에서만 사용할 수 있습니다.", ephemeral=True)
            return
        removed = await self.bot.db.remove_blacklist_entry(interaction.guild.id, user.id)
        await interaction.response.send_message(
            "목록에서 삭제했습니다." if removed else "등록된 항목을 찾지 못했습니다.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Blacklist(bot))
