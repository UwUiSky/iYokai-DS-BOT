"""
cogs/utility/patreon.py
=======================
Patreon (CFG-036): avvia il piccolo server web dei webhook e del ritorno OAuth, ma solo se nel .env ci sono
PATREON_CLIENT_ID, PATREON_CLIENT_SECRET e PATREON_WEBHOOK_SECRET. Senza chiavi non apre nessuna porta e non
scrive errori. Nessun comando: il collegamento parte dal pannello (`core/patreon_service.py`).
Funzioni coperte: CFG-036
Dipende da: core/patreon_server.py, core/patreon_service.py
"""

from __future__ import annotations

import logging

from discord.ext import commands

from core import patreon_server, patreon_service, web_panel_logic
from core.config import config

logger = logging.getLogger("iyokai.patreon")


class PatreonCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._runner = None

    async def cog_load(self) -> None:
        if not patreon_service.acceso():
            logger.info("Patreon: chiavi non impostate, modulo spento.")
            return
        try:
            app = patreon_server.build_app(
                client_id=config.PATREON_CLIENT_ID, client_secret=config.PATREON_CLIENT_SECRET,
                webhook_secret=config.PATREON_WEBHOOK_SECRET, applica_evento=patreon_service.applica_evento,
                completa_collegamento=patreon_service.completa_collegamento,
                url_dopo=config.WEB_PANEL_PUBLIC_URL.rstrip("/") + "/premium?patreon=ok" if config.WEB_PANEL_PUBLIC_URL else "",
                url_conferma=config.WEB_PANEL_PUBLIC_URL.rstrip("/") + "/premium?patreon=conferma" if config.WEB_PANEL_PUBLIC_URL else "",
                cookie_sessione=web_panel_logic.nome_cookie_sessione(config.WEB_PANEL_PUBLIC_URL),
            )
            self._runner = await patreon_server.start_server(app, config.WEB_BIND_HOST, config.PATREON_PORT)
        except OSError:
            logger.exception("Patreon: la porta %s non si apre, modulo spento.", config.PATREON_PORT)

    async def cog_unload(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PatreonCog(bot))
