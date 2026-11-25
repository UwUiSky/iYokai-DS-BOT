"""
cogs/fun/battaglia.py
=====================
Battaglia testuale a turni tra due utenti (/giochi sfide battaglia) e le sue statistiche (/giochi sfide battaglie).
Lo sfidato accetta con un bottone che solo lui può premere; ogni turno agisce solo chi è di turno (attacco, difesa,
abilità) entro 40 secondi, altrimenti perde. Con la puntata le monete di entrambi si tolgono insieme in una sola
transazione (partite_repo.apri_gruppo) e si pagano insieme a fine partita. Il blocco personale è rispettato.
Funzioni coperte: FUN-019
Dipende da: core/battaglia_logic.py, core/repositories/battaglie_repo.py, core/repositories/partite_repo.py
"""

from __future__ import annotations

import logging
import random

import discord
from discord import app_commands
from discord.ext import commands

from cogs.fun.sfide import SG_SFIDE
from core import battaglia_logic as bl
from core.command_groups import CogConGruppi, comando_di_gruppo, togli_comandi_del_cog
from core.database import db
from core.i18n import testo_per
from core.leveling_logic import controlla_puntata
from core.repositories.battaglie_repo import battaglie_repo
from core.repositories.leveling_settings_repo import leveling_settings_repo
from core.repositories.partite_repo import EsitoApertura, partite_repo
from core.repositories.sociale_repo import sociale_repo
from core.ui_base import BaseView
from core.giro_periodico import giro_periodico

logger = logging.getLogger("iyokai.battaglia")
NESSUNA_MENZIONE = discord.AllowedMentions.none()
RNG = random.SystemRandom()
GIOCO = "battaglia"
POSTA_MASSIMA = 100_000
ATTESA_RISPOSTA = 120


class BattagliaView(BaseView):
    def __init__(self, guild_id: int, a: discord.Member, b: discord.Member, puntata: int, moneta: str, rng: random.Random | None = None) -> None:
        super().__init__(timeout=ATTESA_RISPOSTA)
        self.guild_id, self.giocatori, self.puntata, self.moneta = guild_id, {1: a, 2: b}, puntata, moneta
        self.rng = rng or RNG
        self.c = {1: bl.Combattente(), 2: bl.Combattente()}
        self.turno, self.turni = 1, 0
        self.fase = "attesa"  # attesa -> in_corso -> fine
        self.ultimo = ""
        self.messaggio: discord.Interaction | None = None
        self._bottoni_attesa()

    # ---------------------------------------------------------------- schermate
    def _bottoni_attesa(self) -> None:
        self.clear_items()
        for etichetta, stile, funzione in (("Accetta", discord.ButtonStyle.success, self._accetta), ("Rifiuta", discord.ButtonStyle.danger, self._rifiuta)):
            b = discord.ui.Button(label=etichetta, style=stile)
            b.callback = funzione
            self.add_item(b)

    async def _bottoni_gioco(self, interaction: discord.Interaction | None) -> None:
        self.clear_items()
        c = self.c[self.turno]
        voci = (
            (bl.ATTACCO, "btl_b_att", discord.ButtonStyle.danger, False),
            (bl.DIFESA, "btl_b_dif", discord.ButtonStyle.primary, False),
            (bl.ABILITA, "btl_b_abi", discord.ButtonStyle.success, c.ricarica > 0),
        )
        for azione, chiave, stile, spento in voci:
            etichetta = await testo_per(interaction, chiave, pubblica=True) if interaction else chiave
            b = discord.ui.Button(label=etichetta[:80], style=stile, disabled=spento)
            b.callback = self._azione(azione)
            self.add_item(b)

    async def tavolo(self, interaction) -> str:
        righe = []
        for n in (1, 2):
            c = self.c[n]
            guardia = " 🛡️" if c.guardia else ""
            righe.append(await testo_per(interaction, "btl_riga", pubblica=True, nome=self.giocatori[n].mention,
                                         barra=bl.barra(c.pv), pv=c.pv, guardia=guardia))
        posta = f" · {self.puntata} {self.moneta}" if self.puntata else ""
        return "\n".join(righe) + posta

    async def _schermata(self, interaction, extra: str = "") -> str:
        testo = await self.tavolo(interaction)
        if self.ultimo:
            testo += f"\n{self.ultimo}"
        if extra:
            testo += f"\n{extra}"
        return testo

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        if interaction.user.id not in (self.giocatori[1].id, self.giocatori[2].id):
            await interaction.response.send_message(await testo_per(interaction, "sfd_non_tuo"), ephemeral=True)
            return False
        return True

    # ---------------------------------------------------------------- accettazione
    async def _rifiuta(self, interaction: discord.Interaction) -> None:
        if self.fase != "attesa":
            await interaction.response.send_message(await testo_per(interaction, "leveling_gia_fatto"), ephemeral=True)
            return
        self.fase = "fine"
        self.stop()
        await interaction.response.edit_message(content=await testo_per(interaction, "sfd_rifiutato", pubblica=True), view=None)

    async def _accetta(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.giocatori[2].id:  # solo lo sfidato accetta
            await interaction.response.send_message(await testo_per(interaction, "sfd_solo_sfidato"), ephemeral=True)
            return
        if self.fase != "attesa":  # nessun await tra controllo e segno
            await interaction.response.send_message(await testo_per(interaction, "leveling_gia_fatto"), ephemeral=True)
            return
        self.fase = "apertura"
        if self.puntata:
            attesa = (await leveling_settings_repo.get_config(self.guild_id)).impostazioni.attesa_gioco
            esito, chi = await partite_repo.apri_gruppo(
                self.guild_id, [self.giocatori[1].id, self.giocatori[2].id], GIOCO, self.puntata, attesa
            )
            if esito is not EsitoApertura.APERTA:  # nessuna moneta tolta a nessuno
                self.fase = "fine"
                self.stop()
                chiave = "tav_poche" if esito is EsitoApertura.POCHE else "tav_non_puo"
                await interaction.response.edit_message(
                    content=await testo_per(interaction, chiave, chi=f"<@{chi}>", moneta=self.moneta, pubblica=True),
                    view=None, allowed_mentions=NESSUNA_MENZIONE,
                )
                return
        self.fase = "in_corso"
        self.timeout = bl.TEMPO_TURNO  # da qui il tempo è quello del turno: chi non agisce perde
        bl.inizia_turno(self.c[self.turno])
        await self._bottoni_gioco(interaction)
        await interaction.response.edit_message(content=await self._schermata(interaction, await self._chi_tocca(interaction)), view=self,
                                                allowed_mentions=NESSUNA_MENZIONE)

    async def _chi_tocca(self, interaction) -> str:
        return await testo_per(interaction, "btl_turno", pubblica=True, chi=self.giocatori[self.turno].mention, secondi=bl.TEMPO_TURNO)

    # ---------------------------------------------------------------- turni
    def _azione(self, azione: str):
        async def _cb(interaction: discord.Interaction) -> None:
            await self._gioca(interaction, azione)
        return _cb

    async def _gioca(self, interaction: discord.Interaction, azione: str) -> None:
        if self.fase != "in_corso":
            await interaction.response.send_message(await testo_per(interaction, "leveling_gia_fatto"), ephemeral=True)
            return
        if interaction.user.id != self.giocatori[self.turno].id:
            await interaction.response.send_message(await testo_per(interaction, "btl_non_tuo_turno"), ephemeral=True)
            return
        chi_n = self.turno
        chi, altro = self.c[chi_n], self.c[3 - chi_n]
        if not bl.puo_agire(chi, azione):
            await interaction.response.send_message(await testo_per(interaction, "btl_abi_ricarica", n=chi.ricarica), ephemeral=True)
            return
        # Da qui fino al cambio di turno non c'è nessun await: due clic insieme non agiscono due volte.
        esito = bl.esegui(chi, altro, azione, self.rng)
        self.turni += 1
        fine = bl.vincitore(self.c[1], self.c[2], self.turni)
        if fine is None:
            self.turno = 3 - chi_n
            bl.inizia_turno(self.c[self.turno])
        self.ultimo = await self._riga_esito(interaction, esito, self.giocatori[chi_n], self.giocatori[3 - chi_n])
        if fine is not None:
            await self._fine(interaction, fine, "btl_limite" if self.turni >= bl.TURNI_MASSIMI and min(self.c[1].pv, self.c[2].pv) > 0 else "")
            return
        await self._bottoni_gioco(interaction)
        await interaction.response.edit_message(content=await self._schermata(interaction, await self._chi_tocca(interaction)), view=self,
                                                allowed_mentions=NESSUNA_MENZIONE)

    async def _riga_esito(self, interaction, e: bl.Esito, chi, altro) -> str:
        if e.azione == bl.DIFESA:
            chiave = "btl_dif"
        elif e.azione == bl.ABILITA:
            chiave = "btl_abi_vuoto" if e.mancato else "btl_abi_parata" if e.parato else "btl_abi"
        else:
            chiave = "btl_att_parato" if e.parato else "btl_att"
        return await testo_per(interaction, chiave, pubblica=True, chi=chi.mention, altro=altro.mention, danno=e.danno, cura=e.curato)

    # ---------------------------------------------------------------- fine
    async def _fine(self, interaction: discord.Interaction | None, vincitore: int, motivo_chiave: str = "") -> None:
        if self.fase == "fine":
            return
        self.fase = "fine"
        self.stop()
        a, b = self.giocatori[1], self.giocatori[2]
        if self.puntata:
            if vincitore:  # chi vince incassa il doppio, chi perde niente: tutto insieme
                restituzioni = {self.giocatori[vincitore].id: self.puntata * 2, self.giocatori[3 - vincitore].id: 0}
            else:
                restituzioni = {a.id: self.puntata, b.id: self.puntata}
            try:
                await partite_repo.chiudi_gruppo(self.guild_id, GIOCO, restituzioni)
            except Exception:
                logger.exception("Chiusura della battaglia non riuscita")
        if vincitore:
            try:
                await battaglie_repo.registra(self.guild_id, self.giocatori[vincitore].id, self.giocatori[3 - vincitore].id)
            except Exception:
                logger.exception("Statistiche della battaglia non salvate")
        origine = interaction or self.messaggio
        motivo = await testo_per(origine, motivo_chiave, pubblica=True) if motivo_chiave and origine is not None else ""
        if vincitore:
            esito = await testo_per(origine, "btl_vince", pubblica=True, chi=self.giocatori[vincitore].mention, motivo=motivo)
        else:
            esito = await testo_per(origine, "btl_pari", pubblica=True)
        self.clear_items()
        testo = await self._schermata(origine, esito)
        try:
            if interaction is not None:
                await interaction.response.edit_message(content=testo, view=None, allowed_mentions=NESSUNA_MENZIONE)
            elif self.messaggio is not None:
                await self.messaggio.edit_original_response(content=testo, view=None, allowed_mentions=NESSUNA_MENZIONE)
        except discord.HTTPException:
            pass

    async def on_timeout(self) -> None:
        if self.fase == "in_corso":  # chi non agisce perde
            self.ultimo = ""
            await self._fine(None, 3 - self.turno, "btl_tempo")
        elif self.fase == "attesa":
            self.fase = "fine"


class BattagliaCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._rimborsi.start()

    def cog_unload(self) -> None:
        self._rimborsi.cancel()
        togli_comandi_del_cog(self)

    @giro_periodico(minutes=5)
    async def _rimborsi(self) -> None:
        try:
            await partite_repo.rimborsa_scadute()
        except Exception:
            logger.exception("Giro dei rimborsi delle battaglie")

    @_rimborsi.before_loop
    async def _prima(self) -> None:
        await self.bot.wait_until_ready()
        try:  # all'avvio: le battaglie stanno in memoria, quelle rimaste aperte sono perse e si rimborsano
            await partite_repo.rimborsa_gioco(GIOCO)
        except Exception:
            logger.exception("Rimborso delle battaglie all'avvio")

    @comando_di_gruppo("giochi", nome="battaglia", descrizione="Battaglia a turni contro un membro: attacco, difesa e abilità, anche con una puntata.", sottogruppo=SG_SFIDE)
    @app_commands.describe(membro="Chi sfidi", puntata="Monete in palio (0 = solo per divertimento)")
    async def battaglia(self, interaction: discord.Interaction, membro: discord.Member, puntata: app_commands.Range[int, 0, POSTA_MASSIMA] = 0) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return
        if membro.id == interaction.user.id or membro.bot:
            await interaction.response.send_message(await testo_per(interaction, "sfd_bersaglio"), ephemeral=True)
            return
        if await sociale_repo.ha_bloccato(membro.id, interaction.user.id) or await sociale_repo.ha_bloccato(interaction.user.id, membro.id):
            await interaction.response.send_message(await testo_per(interaction, "soc_bloccato"), ephemeral=True)
            return
        if not await db.is_module_active_for_guild(guild.id, "fun"):
            await interaction.response.send_message(await testo_per(interaction, "ping_questo_modulo_non_attivo_su"), ephemeral=True)
            return
        i = (await leveling_settings_repo.get_config(guild.id)).impostazioni
        if puntata:
            if not await db.is_module_active_for_guild(guild.id, "leveling"):
                await interaction.response.send_message(await testo_per(interaction, "ping_questo_modulo_non_attivo_su"), ephemeral=True)
                return
            motivo = controlla_puntata(puntata, i)
            if motivo is not None:
                await interaction.response.send_message(f"❌ {motivo}", ephemeral=True)
                return
        view = BattagliaView(guild.id, interaction.user, membro, puntata, i.currency_name)
        view.messaggio = interaction
        await interaction.response.send_message(
            await testo_per(interaction, "btl_sfida", sfidante=interaction.user.mention, sfidato=membro.mention, posta=puntata, moneta=i.currency_name, pubblica=True),
            view=view, allowed_mentions=discord.AllowedMentions(users=[membro]),
        )

    @comando_di_gruppo("giochi", nome="battaglie", descrizione="Le battaglie vinte e perse di un membro e i migliori del server.", sottogruppo=SG_SFIDE)
    @app_commands.describe(membro="Di chi vuoi le statistiche (di base le tue)")
    async def battaglie(self, interaction: discord.Interaction, membro: discord.Member | None = None) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return
        chi = membro or interaction.user
        vinte, perse = await battaglie_repo.statistiche(guild.id, chi.id)
        righe = [await testo_per(interaction, "btl_stat", chi=chi.mention, vinte=vinte, perse=perse, pubblica=True)]
        for n, (uid, v, p) in enumerate(await battaglie_repo.classifica(guild.id, 5), 1):
            righe.append(f"{n}. <@{uid}> · {v} / {p}")
        await interaction.response.send_message("\n".join(righe), allowed_mentions=NESSUNA_MENZIONE)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BattagliaCog(bot))
