"""
cogs/utility/inneschi.py
========================
Inneschi dei tag (B27): `/admin-automazioni inneschi aggiungi|elenco|togli|avvia-ora`. Un tag parte da solo con una reazione,
a intervalli, a un orario (cron), con un bottone di un embed, quando un ruolo viene dato o tolto. A tempo: scheduler (il giro
dopo si prenota prima di eseguire). Al massimo 25 inneschi per server.
Funzioni coperte: catalogo #128 UTL-047..050, 052, 054 (D69, B27)
Dipende da: cogs/utility/custom_commands.py (esegui_innesco), core/tag_inneschi_logic.py
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core import tag_inneschi_logic as L
from core.bounded_cache import BoundedCache
from core.command_access import Livello, autocomplete_protetto
from core.command_groups import CogConGruppi, SOTTOGRUPPI, comando_di_gruppo
from core.custom_command_logic import MAX_NOME
from core.database import db
from core.i18n import testo_per
from core.nome_logic import normalizza_nome
from core.repositories.custom_command_repo import custom_command_repo
from core.repositories.embed_bottoni_repo import embed_bottoni_repo
from core.repositories.tag_inneschi_repo import tag_inneschi_repo
from core.scheduler import scheduler

logger = logging.getLogger("iyokai.inneschi")

MODULE_CUSTOM_COMMANDS = "custom_commands"
_NESSUNA = discord.AllowedMentions.none()
_TTL = 60
MAX_PER_EVENTO = 3  # un'emoji o un ruolo non fa partire più di 3 tag insieme
_SCELTE_TIPO = [app_commands.Choice(name=n, value=v) for n, v in (
    ("reazione (un'emoji sotto un messaggio)", "reazione"), ("intervallo (ogni tanto, da 10 minuti)", "intervallo"),
    ("orario (cron a 5 campi)", "orario"), ("bottone di un embed", "bottone"),
    ("ruolo dato", "ruolo_dato"), ("ruolo tolto", "ruolo_tolto"))]


class InneschiCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._cache: BoundedCache = BoundedCache(512)

    @property
    def tag_cog(self):
        return self.bot.get_cog("CustomCommandsCog")

    async def cog_load(self) -> None:
        await super().cog_load()
        scheduler.register_handler(L.AZIONE_INNESCO, self.handle_innesco)

    # ------------------------------------------------------------ archivio con copia breve
    async def _inneschi(self, guild_id: int, tipo: str):
        voce = self._cache.get((guild_id, tipo))
        if voce is not None and voce[0] > time.monotonic():
            return voce[1]
        righe = await tag_inneschi_repo.per_tipo(guild_id, tipo)
        self._cache.set((guild_id, tipo), (time.monotonic() + _TTL, righe))
        return righe

    async def _pronto(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return False
        if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_CUSTOM_COMMANDS):
            await interaction.response.send_message(await testo_per(interaction, "ping_questo_modulo_non_attivo_su"), ephemeral=True)
            return False
        return True

    async def _dire(self, interaction: discord.Interaction, chiave: str, **valori) -> None:
        await interaction.response.send_message(await testo_per(interaction, chiave, **valori), ephemeral=True, allowed_mentions=_NESSUNA)

    # ------------------------------------------------------------ ascolto
    async def _fai_partire(self, guild: discord.Guild, righe, canale, membro) -> None:
        tag_cog = self.tag_cog
        if tag_cog is None or not await db.is_module_active_for_guild(guild.id, MODULE_CUSTOM_COMMANDS):
            return
        for r in righe[:MAX_PER_EVENTO]:
            try:
                await tag_cog.esegui_innesco(guild, r["tag"], canale, membro=membro)
            except Exception:
                logger.warning("Innesco %s del tag %s fallito.", r["id"], r["tag"], exc_info=True)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        membro = payload.member
        if payload.guild_id is None or membro is None or membro.bot:
            return
        righe = [r for r in await self._inneschi(payload.guild_id, "reazione")
                 if L.stessa_emoji(r["valore"], str(payload.emoji)) and r["canale_id"] in (None, payload.channel_id)]
        guild = self.bot.get_guild(payload.guild_id)
        canale = guild.get_channel_or_thread(payload.channel_id) if guild and righe else None
        if righe and canale is not None:
            await self._fai_partire(guild, righe, canale, membro)

    @commands.Cog.listener()
    async def on_member_update(self, prima: discord.Member, dopo: discord.Member) -> None:
        if dopo.bot:
            return
        prima_ids, dopo_ids = {r.id for r in prima.roles}, {r.id for r in dopo.roles}
        for tipo, cambiati in (("ruolo_dato", dopo_ids - prima_ids), ("ruolo_tolto", prima_ids - dopo_ids)):
            if not cambiati:
                continue
            for r in await self._inneschi(dopo.guild.id, tipo):
                canale = dopo.guild.get_channel(r["canale_id"]) if r["canale_id"] else None
                if r["valore"].isdigit() and int(r["valore"]) in cambiati and canale is not None:
                    await self._fai_partire(dopo.guild, [r], canale, dopo)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, canale: discord.abc.GuildChannel) -> None:
        """Un innesco che scriveva in un canale sparito non ha più dove andare: si toglie."""
        if await tag_inneschi_repo.togli_per_canale(canale.guild.id, canale.id):
            self._cache.clear()

    # ------------------------------------------------------------ scheduler
    async def handle_innesco(self, guild_id: int, user_id: int, payload: dict) -> None:
        """Giro di un innesco a tempo. Se l'innesco è stato tolto la catena finisce; il giro dopo si prenota prima di eseguire."""
        riga = await tag_inneschi_repo.prendi_per_id(payload.get("innesco_id", 0))
        if riga is None or riga["tipo"] not in L.TIPI_A_TEMPO:
            return
        adesso = datetime.now(timezone.utc)
        prossimo = L.prossimo_giro(riga["tipo"], riga["valore"], adesso)
        if prossimo is not None:
            await scheduler.schedule(riga["guild_id"], 0, L.AZIONE_INNESCO, prossimo, {"innesco_id": riga["id"]})
        guild = self.bot.get_guild(riga["guild_id"])
        canale = guild.get_channel(riga["canale_id"]) if guild and riga["canale_id"] else None
        if canale is None or L.escluso(riga["escludi"], adesso):
            return
        await self._fai_partire(guild, [riga], canale, None)

    # ------------------------------------------------------------ comandi
    @autocomplete_protetto(Livello.ADMIN)
    async def _completa_tag(self, interaction: discord.Interaction, current: str):
        if interaction.guild is None:
            return []
        nomi = await custom_command_repo.search_names(interaction.guild.id, current.lower(), 25)
        return [app_commands.Choice(name=n, value=n) for n in nomi]

    @autocomplete_protetto(Livello.ADMIN)
    async def _completa_innesco(self, interaction: discord.Interaction, current: str):
        if interaction.guild is None:
            return []
        scelte = [app_commands.Choice(name=f"{r['id']} · {r['tipo']} {r['valore']} → {r['tag']}"[:100], value=r["id"])
                  for r in await tag_inneschi_repo.elenco(interaction.guild.id)]
        return [s for s in scelte if current.lower() in s.name.lower()][:25]

    @comando_di_gruppo("admin-automazioni", nome="aggiungi", descrizione="Fa partire un tag da solo: reazione, intervallo, orario, bottone, ruolo.",
                       sottogruppo=SOTTOGRUPPI["admin-automazioni inneschi"])
    @app_commands.describe(tag="Il tag da far partire", tipo="Cosa lo fa partire", valore="Emoji, 30m, cron (0 9 * * 1) o embed:posizione",
                           ruolo="Il ruolo (per ruolo dato o tolto)", canale="Dove scrive (serve a tempo e a ruolo)",
                           escludi="Ore e giorni da saltare, per esempio 23-7 sab dom")
    @app_commands.choices(tipo=_SCELTE_TIPO)
    @app_commands.autocomplete(tag=_completa_tag)
    async def aggiungi(self, interaction: discord.Interaction, tag: app_commands.Range[str, 1, MAX_NOME], tipo: app_commands.Choice[str],
                       valore: app_commands.Range[str, 0, L.MAX_VALORE] = "", ruolo: discord.Role | None = None,
                       canale: discord.TextChannel | None = None, escludi: app_commands.Range[str, 0, L.MAX_ESCLUDI] = "") -> None:
        if not await self._pronto(interaction):
            return
        guild, tipo_v = interaction.guild, tipo.value
        nome = normalizza_nome(tag)
        if nome is None or await custom_command_repo.get_tag(guild.id, nome) is None:
            await self._dire(interaction, "inn_tag_manca")
            return
        if tipo_v in ("ruolo_dato", "ruolo_tolto"):
            valore = str(ruolo.id) if ruolo else ""
        pulito, errore = L.valida(tipo_v, valore)
        if errore is None and tipo_v in L.TIPI_A_TEMPO + ("ruolo_dato", "ruolo_tolto") and canale is None:
            errore = "inn_canale_serve"
        if errore is None and tipo_v == "bottone":
            nome_embed, _, posizione = pulito.partition(":")
            bottone = await embed_bottoni_repo.prendi(guild.id, nome_embed, int(posizione))
            if bottone is None or bottone.tipo != "tag":
                errore = "inn_bottone_non_valido"
        solo = L.leggi_escludi(escludi)
        if errore is None and solo is None:
            errore = "inn_escludi_non_valido"
        if errore is None and canale is not None and not canale.permissions_for(guild.me).send_messages:
            errore = "inn_canale_senza_permesso"
        if errore is not None:
            await self._dire(interaction, errore)
            return
        esito, nuovo_id = await tag_inneschi_repo.aggiungi(guild.id, nome, tipo_v, pulito, canale.id if canale else None, solo, interaction.user.id)
        if esito != "ok":
            await self._dire(interaction, {"pieno": "inn_pieno", "esiste": "inn_esiste"}[esito], massimo=L.MAX_INNESCHI)
            return
        self._cache.clear()
        if tipo_v in L.TIPI_A_TEMPO:
            await scheduler.schedule(guild.id, 0, L.AZIONE_INNESCO, L.prossimo_giro(tipo_v, pulito, datetime.now(timezone.utc)), {"innesco_id": nuovo_id})
        await self._dire(interaction, "inn_aggiunto", numero=nuovo_id)

    @comando_di_gruppo("admin-automazioni", nome="elenco", descrizione="Gli inneschi del server.", sottogruppo=SOTTOGRUPPI["admin-automazioni inneschi"])
    async def elenco(self, interaction: discord.Interaction) -> None:
        if not await self._pronto(interaction):
            return
        righe = await tag_inneschi_repo.elenco(interaction.guild.id)
        if not righe:
            await self._dire(interaction, "inn_elenco_vuoto")
            return
        voci = [f"`{r['id']}` · {r['tipo']} `{r['valore']}` → **{r['tag']}**"
                + (f" · <#{r['canale_id']}>" if r["canale_id"] else "") + (f" · salta {r['escludi']}" if r["escludi"] else "") for r in righe]
        testo = (await testo_per(interaction, "inn_elenco_titolo", n=len(righe), massimo=L.MAX_INNESCHI)) + "\n" + "\n".join(voci)
        await interaction.response.send_message(testo[:2000], ephemeral=True, allowed_mentions=_NESSUNA)

    @comando_di_gruppo("admin-automazioni", nome="togli", descrizione="Toglie un innesco.", sottogruppo=SOTTOGRUPPI["admin-automazioni inneschi"])
    @app_commands.describe(numero="L'innesco (scegli dall'elenco)")
    @app_commands.autocomplete(numero=_completa_innesco)
    async def togli(self, interaction: discord.Interaction, numero: app_commands.Range[int, 1, 2**31]) -> None:
        if not await self._pronto(interaction):
            return
        fatto = await tag_inneschi_repo.togli(interaction.guild.id, numero)
        self._cache.clear()
        await self._dire(interaction, "inn_tolto" if fatto else "inn_non_trovato")

    @comando_di_gruppo("admin-automazioni", nome="avvia-ora", descrizione="Fa partire un innesco subito, per provarlo.",
                       sottogruppo=SOTTOGRUPPI["admin-automazioni inneschi"])
    @app_commands.describe(numero="L'innesco (scegli dall'elenco)")
    @app_commands.autocomplete(numero=_completa_innesco)
    async def avvia_ora(self, interaction: discord.Interaction, numero: app_commands.Range[int, 1, 2**31]) -> None:
        if not await self._pronto(interaction):
            return
        riga = await tag_inneschi_repo.prendi(interaction.guild.id, numero)
        if riga is None:
            await self._dire(interaction, "inn_non_trovato")
            return
        canale = interaction.guild.get_channel(riga["canale_id"]) if riga["canale_id"] else interaction.channel
        if canale is None or self.tag_cog is None:
            await self._dire(interaction, "inn_avvio_fallito")
            return
        await interaction.response.defer(ephemeral=True)
        membro = None if riga["tipo"] in L.TIPI_A_TEMPO else interaction.user
        rifiuto = await self.tag_cog.esegui_innesco(interaction.guild, riga["tag"], canale, membro=membro)
        await interaction.followup.send(await testo_per(interaction, rifiuto or "inn_avviato"), ephemeral=True, allowed_mentions=_NESSUNA)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(InneschiCog(bot))
