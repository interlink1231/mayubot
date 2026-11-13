from __future__ import annotations

import logging

import discord
from discord.ext import commands

from mayubot.config import Settings
from mayubot.database import Database

log = logging.getLogger("mayubot")


class MayuBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        intents.message_content = True
        intents.moderation = True
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        self.settings = settings
        self.db = Database(settings.database_path)

    async def setup_hook(self) -> None:
        await self.db.initialize()
        for extension in (
            "mayubot.cogs.security",
            "mayubot.cogs.automod",
            "mayubot.cogs.antiraid",
            "mayubot.cogs.server_tags",
        ):
            await self.load_extension(extension)
            log.info("Extension loaded: %s", extension)
        if self.settings.sync_commands:
            if self.settings.test_guild_id:
                guild = discord.Object(id=self.settings.test_guild_id)
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
            else:
                synced = await self.tree.sync()
            log.info("Synced %d application commands", len(synced))

    async def on_ready(self) -> None:
        log.info("Logged in as %s (%s)", self.user, self.user.id if self.user else "?")
        log.info("Serving %d guild(s)", len(self.guilds))

    async def on_guild_join(self, guild: discord.Guild) -> None:
        await self.db.ensure_guild(guild.id)
        log.info("Joined guild %s (%s)", guild.name, guild.id)
