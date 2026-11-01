"""
cogs/ai/bozze.py
================
Funzione richiesta che non esiste: quando l'owner approva la richiesta di un comando, l'AI scrive una bozza del codice
(tipo `codice`) e, se `GITHUB_BOZZE_TOKEN` e `GITHUB_BOZZE_REPO` ci sono, apre una pull request in bozza. L'owner riceve
il link (o la bozza come file) in privato. Il bot non unisce mai da solo. Al massimo 5 bozze al giorno.
Funzioni coperte: SPEC §25.100 (AI-R-107)
"""

from __future__ import annotations

import io
import logging

import discord
from discord.ext import commands, tasks

from cogs.ai._comune import chiedi, registra_modulo_ai
from core import ai_bozza_logic as logica
from core.ai_servizio import RichiestaAI
from core.bot_ready import attendi_bot_pronto
from core.config import config
from core.github_bozze import github_bozze
from core.repositories.ai_bozze_repo import ai_bozze_repo

logger = logging.getLogger("iyokai.ai_bozze")


async def prepara_bozza(r: logica.Richiesta) -> tuple[str, str | None, str] | None:
    """(stato, indirizzo della pull request, testo della bozza) oppure None se l'AI non c'è (si riprova dopo)."""
    risposta, _ = await chiedi(RichiestaAI(
        user_id=config.OWNER_ID, funzione="bozza_funzione", tipo="codice", testo=logica.testo_per_ai(r), guild_id=None,
        fascia="alta", istruzioni=logica.ISTRUZIONI, messaggi_utenti=True, conta_utente=False, riusa=False,
    ))
    if risposta is None or not risposta.testo.strip():
        return None
    bozza = risposta.testo[: logica.MAX_BOZZA]
    url = await github_bozze().apri_bozza(
        logica.nome_ramo(r), logica.percorso_file(r), logica.contenuto_file(r, bozza), logica.titolo_pr(r), logica.corpo_pr(r)
    )
    return ("pr_aperta" if url else "pronta"), url, bozza


class AiBozzeCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self._ciclo.start()

    async def cog_unload(self) -> None:
        self._ciclo.cancel()

    @tasks.loop(minutes=10)
    async def _ciclo(self) -> None:
        try:
            await self.giro()
        except Exception:  # noqa: BLE001
            logger.warning("Giro delle bozze non riuscito.", exc_info=True)

    @_ciclo.before_loop
    async def _prima(self) -> None:
        await attendi_bot_pronto(self.bot)

    async def giro(self) -> int:
        """Prepara le bozze mancanti entro il tetto del giorno. Restituisce quante ne ha fatte."""
        fatte = 0
        for r in await ai_bozze_repo.da_preparare():
            if not logica.sotto_il_tetto(await ai_bozze_repo.fatte_oggi()):
                break
            esito = await prepara_bozza(r)
            if esito is None:
                break  # AI ferma o non adatta: nulla viene salvato, si riprova al prossimo giro
            stato, url, bozza = esito
            await ai_bozze_repo.salva(r.id, stato, bozza, url)
            await self._avvisa_owner(r, stato, url, bozza)
            fatte += 1
        return fatte

    async def _avvisa_owner(self, r: logica.Richiesta, stato: str, url: str | None, bozza: str) -> None:
        try:
            owner = self.bot.get_user(config.OWNER_ID) or await self.bot.fetch_user(config.OWNER_ID)
            testo = f"Bozza dell'AI per la richiesta #{r.id} ({r.nome[:60]}). " + (
                f"Pull request in bozza: {url}" if url else "Allego il testo: controllalo prima di usarlo."
            )
            file = None if url else discord.File(io.BytesIO(logica.contenuto_file(r, bozza).encode()), filename=f"bozza_{r.id}.md")
            await owner.send(testo, file=file, allowed_mentions=discord.AllowedMentions.none()) if file else await owner.send(
                testo, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            logger.info("Owner non avvisato della bozza %s.", r.id)


async def setup(bot: commands.Bot) -> None:
    registra_modulo_ai()
    await bot.add_cog(AiBozzeCog(bot))
