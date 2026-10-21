"""
cogs/utility/autoroles.py
=========================
Ruoli automatici all'ingresso, ruoli ridati a chi rientra entro 30 giorni,
ruoli dati dopo un ritardo (NF-07, SPEC §22.1-22.3); condizioni su altri
ruoli, ruolo ridato se tolto, sincronizzazione dei membri già presenti
(catalogo #123, RUO-034..038). Comandi: i comandi `auto-...` di
`/gestione ruoli`; la logica è in core/autorole_logic.py.
Funzioni coperte: SPEC §22 (NF-07)
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.autorole_logic import (
    MAX_GIORNI_MEMORIA,
    MAX_REGOLE,
    MAX_RITARDO_SECONDI,
    membro_in_attesa,
    piano_ingresso,
    regola_vale_per,
    ruoli_da_ricordare,
    ruoli_da_ridare,
    ruoli_da_ridare_se_tolti,
    ruoli_da_sincronizzare,
)
from cogs.utility.role_menus import ROLEMENU_TEMP_ACTION_TYPE
from core.birthday_worker import BIRTHDAY_ROLE_ACTION_TYPE
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.premium import PremiumModule, registry
from core.repositories.autorole_repo import autorole_repo
from core.repositories.verify_repo import verify_repo
from core.role_safety import check_role_assignable, motivo_ruolo_automatico_non_assegnabile
from core.ruoli_strumenti_logic import PAUSA_MASSA_SECONDI, RUOLI_TEMPORANEI_ACTION_TYPE
from core.scheduler import in_seconds, scheduler
from core.security_raid_state import DURATA_RAID_SECONDI, raid_in_corso

logger = logging.getLogger("iyokai.autoroles")

MODULE_AUTOROLES = "autoroles"
MODULE_VERIFY = "verify"
AUTOROLE_ACTION_TYPE = "autorole_give"
# Azioni dello scheduler che tolgono un ruolo dopo un po': quei ruoli non vanno ricordati.
TIPI_RUOLO_A_TEMPO = (ROLEMENU_TEMP_ACTION_TYPE, BIRTHDAY_ROLE_ACTION_TYPE, RUOLI_TEMPORANEI_ACTION_TYPE)

# «Ridai se tolto»: al massimo tante volte per membro e ruolo in una finestra. Contro un
# altro bot (o un'altra funzione) che lo toglie sempre: senza tetto il botta e risposta è infinito.
MAX_RIDAI_PER_FINESTRA = 3
FINESTRA_RIDAI_SECONDI = 600

_SG_RUOLI = ("ruoli", "Ruoli: ruoli-premio per livello e menu di ruoli")


def _riga_regola(regola) -> str:
    riga = f"<@&{regola.role_id}> — {_testo_ritardo(regola.delay_seconds)}"
    if regola.richiesti:
        riga += " — solo con " + " ".join(f"<@&{r}>" for r in regola.richiesti)
    if regola.esclusi:
        riga += " — non con " + " ".join(f"<@&{r}>" for r in regola.esclusi)
    if regola.ridai:
        riga += " — ridato se tolto"
    return riga


def _ruoli_a_tempo(azione: dict) -> set:
    """Gli ID dei ruoli che un'azione a tempo toglierà (un ruolo o la lista `dati`)."""
    payload = azione["payload"]
    return {payload.get("role_id"), *payload.get("dati", [])}


def _testo_ritardo(secondi: int) -> str:
    if secondi <= 0:
        return "subito"
    if secondi % 86400 == 0:
        return f"dopo {secondi // 86400} g"
    if secondi % 3600 == 0:
        return f"dopo {secondi // 3600} h"
    return f"dopo {max(secondi // 60, 1)} min"


class AutorolesCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Un task di sincronizzazione per server: il riferimento lo tiene vivo e permette di fermarlo.
        self.sincronie: dict[int, asyncio.Task] = {}
        # (server, membro, ruolo) -> istanti in cui il ruolo è stato ridato
        self._ridati: dict[tuple[int, int, int], list[float]] = {}

    async def cog_unload(self) -> None:
        for task in self.sincronie.values():
            task.cancel()
        self.sincronie.clear()
        await super().cog_unload()

    # ================================================================
    # Assegnazione
    # ================================================================
    async def _ruolo_verificato_atteso(self, guild: discord.Guild) -> int | None:
        """L'ID del ruolo "verificato" se la verifica del server è attiva, altrimenti None."""
        if not await db.is_module_active_for_guild(guild.id, MODULE_VERIFY):
            return None
        return (await verify_repo.get_config(guild.id)).verified_role_id

    async def _assegna(self, member: discord.Member, ruoli_id: list[int]) -> None:
        """Dà i ruoli che il bot può assegnare; salta gli altri con un avviso nel log."""
        da_dare: list[discord.Role] = []
        for rid in ruoli_id:
            motivo = motivo_ruolo_automatico_non_assegnabile(member.guild, rid)
            if motivo is not None:
                logger.warning("Ruolo automatico %s saltato nel server %s: %s", rid, member.guild.id, motivo)
                continue
            da_dare.append(member.guild.get_role(rid))
        if not da_dare:
            return
        try:
            await member.add_roles(*da_dare, reason="Ruolo automatico")
        except discord.HTTPException as errore:
            logger.warning("Ruoli automatici non dati a %s nel server %s: %s", member.id, member.guild.id, errore)

    async def _ruoli_ricordati_da_ridare(self, member: discord.Member) -> list[int]:
        """I ruoli che aveva prima di uscire (se la memoria è accesa e il rientro è entro i giorni)."""
        config = await autorole_repo.get_config(member.guild.id)
        if not config.remember_enabled:
            return []
        ricordati = await autorole_repo.pop_memory(member.guild.id, member.id)
        if ricordati is None:
            return []
        return ruoli_da_ridare(ricordati.role_ids, ricordati.left_at, datetime.now(timezone.utc), config.remember_days)

    async def _applica_regole(self, member: discord.Member) -> None:
        """Ruoli ricordati e regole: subito o in coda sullo scheduler. Si arriva qui solo quando il
        membro non è più in attesa (schermata di verifica / ruolo Verify), mai prima."""
        if member.bot:
            return
        guild = member.guild
        regole = await autorole_repo.list_rules(guild.id)
        posseduti = {r.id for r in member.roles}
        subito, dopo = piano_ingresso(regole, is_bot=member.bot, ruoli_posseduti=posseduti)
        ricordati = [r for r in await self._ruoli_ricordati_da_ridare(member) if r not in posseduti and r not in subito]
        pausa = raid_in_corso(guild.id)
        if pausa:
            # Durante un raid i ruoli non si danno: si programmano a raid finito.
            dopo = dopo + [(rid, 0) for rid in subito + ricordati]
            subito, programmati_ricordati = [], set(ricordati)
        else:
            subito = subito + ricordati
            programmati_ricordati = set()
        if subito:
            await self._assegna(member, subito)
        for rid, attesa in dopo:
            secondi = attesa + (DURATA_RAID_SECONDI if pausa else 0)
            payload = {"role_id": rid}
            if rid in programmati_ricordati:
                payload["ricordato"] = True  # niente regola dietro: non va ricontrollata allo scatto
            await scheduler.schedule(guild.id, member.id, AUTOROLE_ACTION_TYPE, in_seconds(secondi), payload)

    async def handle_autorole_give(self, guild_id: int, user_id: int, payload: dict) -> None:
        """Handler dello scheduler: dà un ruolo ritardato se la regola c'è ancora e il membro pure."""
        guild = self.bot.get_guild(guild_id)
        role_id = payload.get("role_id")
        if guild is None or role_id is None:
            return
        member = guild.get_member(user_id)
        if member is None:
            return
        if not payload.get("ricordato"):
            regola = next((r for r in await autorole_repo.list_rules(guild_id) if r.role_id == role_id), None)
            if regola is None or not regola_vale_per(regola, {r.id for r in member.roles}):
                return
        if member.pending:
            return  # non ha ancora accettato le regole: i ruoli arrivano da on_member_update
        if raid_in_corso(guild_id):
            await scheduler.schedule(
                guild_id, user_id, AUTOROLE_ACTION_TYPE, in_seconds(DURATA_RAID_SECONDI), payload
            )
            return
        if role_id in {r.id for r in member.roles}:
            return
        await self._assegna(member, [role_id])

    # ================================================================
    # Eventi
    # ================================================================
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot:
            return
        if not await db.is_module_active_for_guild(member.guild.id, MODULE_AUTOROLES):
            return

        verificato = await self._ruolo_verificato_atteso(member.guild)
        if membro_in_attesa(
            member.pending, verificato is not None, verificato in {r.id for r in member.roles}
        ):
            return  # i ruoli arrivano da on_member_update, a verifica o regole accettate
        await self._applica_regole(member)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if after.bot:
            return
        ruoli_prima = {r.id for r in before.roles}
        ruoli_dopo = {r.id for r in after.roles}
        ha_accettato = before.pending and not after.pending
        verificato_ora = False
        if ruoli_prima - ruoli_dopo and not after.pending:
            await self._ridai_se_tolti(after, ruoli_prima, ruoli_dopo)
        if not ha_accettato:
            # Solo il passaggio al ruolo "verificato" interessa: controllo economico prima.
            nuovi = ruoli_dopo - ruoli_prima
            if not nuovi:
                return
        if not await db.is_module_active_for_guild(after.guild.id, MODULE_AUTOROLES):
            return
        verificato = await self._ruolo_verificato_atteso(after.guild)
        if verificato is not None and verificato in (ruoli_dopo - ruoli_prima):
            verificato_ora = True
        if not (ha_accettato or verificato_ora):
            return
        if membro_in_attesa(after.pending, verificato is not None, verificato in ruoli_dopo):
            return
        await self._applica_regole(after)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if member.bot:
            return
        if not await db.is_module_active_for_guild(member.guild.id, MODULE_AUTOROLES):
            return
        config = await autorole_repo.get_config(member.guild.id)
        if not config.remember_enabled:
            return
        # I ruoli a tempo (menu di ruoli, compleanno) non si ricordano: al rientro diventerebbero permanenti.
        a_tempo = {
            role_id
            for tipo in TIPI_RUOLO_A_TEMPO
            for a in await scheduler.list_pending_for_user(member.id, tipo, 100)
            if a["guild_id"] == member.guild.id
            for role_id in _ruoli_a_tempo(a)
        }
        ruoli = [r for r in ruoli_da_ricordare(member.roles) if r not in a_tempo]
        if not ruoli:
            return
        await autorole_repo.save_memory(member.guild.id, member.id, ruoli, datetime.now(timezone.utc))

    async def _ridai_se_tolti(self, member: discord.Member, prima: set[int], dopo: set[int]) -> None:
        """RUO-036: il ruolo automatico con «ridai se tolto» torna a chi ne ha ancora diritto."""
        if not await db.is_module_active_for_guild(member.guild.id, MODULE_AUTOROLES):
            return
        da_ridare = ruoli_da_ridare_se_tolti(await autorole_repo.list_rules(member.guild.id), prima, dopo)
        da_ridare = [rid for rid in da_ridare if self._puo_ridare(member.guild.id, member.id, rid)]
        if da_ridare:
            await self._assegna(member, da_ridare)

    def _puo_ridare(self, guild_id: int, user_id: int, role_id: int) -> bool:
        """Tetto di MAX_RIDAI_PER_FINESTRA ridati per membro e ruolo ogni FINESTRA_RIDAI_SECONDI."""
        ora = time.monotonic()
        if len(self._ridati) > 5000:
            self._ridati = {k: v for k, v in self._ridati.items() if v and ora - v[-1] < FINESTRA_RIDAI_SECONDI}
        chiave = (guild_id, user_id, role_id)
        recenti = [t for t in self._ridati.get(chiave, []) if ora - t < FINESTRA_RIDAI_SECONDI]
        if len(recenti) >= MAX_RIDAI_PER_FINESTRA:
            self._ridati[chiave] = recenti
            logger.warning("Ruolo %s tolto di continuo a %s nel server %s: smetto di ridarlo.", role_id, user_id, guild_id)
            return False
        recenti.append(ora)
        self._ridati[chiave] = recenti
        return True

    async def sincronizza(self, guild: discord.Guild, canale) -> tuple[int, int]:
        """
        RUO-038: dà i ruoli automatici mancanti ai membri già presenti (non bot, non in attesa),
        con una pausa per membro. Restituisce (membri cambiati, errori) e scrive l'esito nel canale.
        """
        cambiati = errori = 0
        try:
            if not guild.chunked:
                await guild.chunk()
            regole = await autorole_repo.list_rules(guild.id)
            for member in list(guild.members):
                if member.bot or member.pending:
                    continue
                mancanti = ruoli_da_sincronizzare(regole, {r.id for r in member.roles})
                ruoli = [
                    guild.get_role(rid) for rid in mancanti
                    if motivo_ruolo_automatico_non_assegnabile(guild, rid) is None
                ]
                if not ruoli:
                    continue
                try:
                    await member.add_roles(*ruoli, reason="Sincronizzazione dei ruoli automatici")
                    cambiati += 1
                except discord.HTTPException:
                    errori += 1
                await asyncio.sleep(PAUSA_MASSA_SECONDI)
        finally:
            self.sincronie.pop(guild.id, None)
        try:
            await canale.send(
                f"Sincronizzazione dei ruoli automatici finita: {cambiati} membri aggiornati, {errori} errori.",
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException:
            logger.warning("Esito della sincronizzazione non inviato nel server %s", guild.id)
        return cambiati, errori

    # ================================================================
    # Comandi
    # ================================================================
    async def _modulo_attivo(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return False
        if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_AUTOROLES):
            await interaction.response.send_message(
                "Questo modulo non è attivo su questo server. "
                "Un amministratore può attivarlo con /admin setup attiva.",
                ephemeral=True,
            )
            return False
        return True

    @comando_di_gruppo(
        "gestione",
        nome="auto-aggiungi",
        descrizione="Aggiungi un ruolo dato in automatico a chi entra.",
        sottogruppo=_SG_RUOLI,
    )
    @app_commands.describe(
        ruolo="Il ruolo da dare a chi entra",
        ritardo_minuti="Attesa prima di darlo (0 = subito, al massimo 7 giorni)",
        solo_con="Dallo solo a chi ha già questo ruolo",
        non_con="Non darlo a chi ha questo ruolo",
        ridai_se_tolto="Se qualcuno lo toglie, il bot lo ridà",
    )
    async def auto_aggiungi(
        self,
        interaction: discord.Interaction,
        ruolo: discord.Role,
        ritardo_minuti: app_commands.Range[int, 0, MAX_RITARDO_SECONDI // 60] = 0,
        solo_con: discord.Role | None = None,
        non_con: discord.Role | None = None,
        ridai_se_tolto: bool = False,
    ) -> None:
        if not await self._modulo_attivo(interaction):
            return
        motivo = check_role_assignable(interaction.guild, ruolo, interaction.user, self_service=True)
        if motivo is not None:
            await interaction.response.send_message(motivo, ephemeral=True)
            return
        ok = await autorole_repo.add_rule(
            interaction.guild.id,
            ruolo.id,
            ritardo_minuti * 60,
            created_by=interaction.user.id,
            richiesti=[solo_con.id] if solo_con else [],
            esclusi=[non_con.id] if non_con else [],
            ridai=ridai_se_tolto,
        )
        if not ok:
            await interaction.response.send_message(
                f"Questo server ha già {MAX_REGOLE} ruoli automatici: togline uno prima.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            f"{ruolo.mention} sarà dato a chi entra {_testo_ritardo(ritardo_minuti * 60)}.",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @comando_di_gruppo(
        "gestione",
        nome="auto-rimuovi",
        descrizione="Togli un ruolo dato in automatico a chi entra.",
        sottogruppo=_SG_RUOLI,
    )
    @app_commands.describe(ruolo="Il ruolo da non dare più")
    async def auto_rimuovi(self, interaction: discord.Interaction, ruolo: discord.Role) -> None:
        if not await self._modulo_attivo(interaction):
            return
        tolto = await autorole_repo.remove_rule(interaction.guild.id, ruolo.id)
        testo = (
            f"{ruolo.mention} non sarà più dato a chi entra."
            if tolto
            else f"{ruolo.mention} non era tra i ruoli automatici."
        )
        await interaction.response.send_message(
            testo, ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
        )

    @comando_di_gruppo(
        "gestione",
        nome="auto-elenco",
        descrizione="Mostra i ruoli automatici del server.",
        sottogruppo=_SG_RUOLI,
    )
    async def auto_elenco(self, interaction: discord.Interaction) -> None:
        if not await self._modulo_attivo(interaction):
            return
        regole = await autorole_repo.list_rules(interaction.guild.id)
        config = await autorole_repo.get_config(interaction.guild.id)
        righe = [_riga_regola(r) for r in regole] or [
            "Nessun ruolo automatico."
        ]
        ricorda = (
            f"Ruoli ridati a chi rientra entro {config.remember_days} giorni: attivo."
            if config.remember_enabled
            else "Ruoli ridati a chi rientra: spento."
        )
        embed = discord.Embed(
            title="Ruoli automatici", description="\n".join(righe)[:4000] + f"\n\n{ricorda}"
        )
        await interaction.response.send_message(
            embed=embed, ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
        )

    @comando_di_gruppo(
        "gestione",
        nome="auto-ricorda",
        descrizione="Ridai i ruoli a chi esce e rientra entro un certo tempo.",
        sottogruppo=_SG_RUOLI,
    )
    @app_commands.describe(
        attivo="Ricordare i ruoli di chi esce?",
        giorni=f"Entro quanti giorni dal rientro (al massimo {MAX_GIORNI_MEMORIA})",
    )
    async def auto_ricorda(
        self,
        interaction: discord.Interaction,
        attivo: bool,
        giorni: app_commands.Range[int, 1, MAX_GIORNI_MEMORIA] = MAX_GIORNI_MEMORIA,
    ) -> None:
        if not await self._modulo_attivo(interaction):
            return
        await autorole_repo.set_remember(interaction.guild.id, attivo, giorni)
        testo = (
            f"D'ora in poi chi esce e rientra entro {giorni} giorni riprende i suoi ruoli."
            if attivo
            else "Ruoli di chi esce non più ricordati; quelli già salvati sono stati cancellati."
        )
        await interaction.response.send_message(testo, ephemeral=True)

    @comando_di_gruppo(
        "gestione",
        nome="auto-sincronizza",
        descrizione="Dai i ruoli automatici anche ai membri già nel server.",
        sottogruppo=_SG_RUOLI,
    )
    async def auto_sincronizza(self, interaction: discord.Interaction) -> None:
        if not await self._modulo_attivo(interaction):
            return
        guild = interaction.guild
        if guild.id in self.sincronie:
            await interaction.response.send_message("Una sincronizzazione è già in corso.", ephemeral=True)
            return
        if not await autorole_repo.list_rules(guild.id):
            await interaction.response.send_message("Non ci sono ruoli automatici da dare.", ephemeral=True)
            return
        self.sincronie[guild.id] = asyncio.create_task(self.sincronizza(guild, interaction.channel))
        await interaction.response.send_message(
            "Sincronizzazione avviata: un membro al secondo. L'esito arriva in questo canale.", ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_AUTOROLES,
            display_name="Ruoli automatici",
            category="utility",
            description="Ruoli dati a chi entra (anche dopo un ritardo) e ridati a chi rientra.",
            premium_capable=False,
        )
    )
    cog = AutorolesCog(bot)
    await bot.add_cog(cog)
    scheduler.register_handler(AUTOROLE_ACTION_TYPE, cog.handle_autorole_give)
