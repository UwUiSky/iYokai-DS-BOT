"""
cogs/fun/tavolo.py
==================
Tris e forza 4 tra due utenti, anche con una puntata (/giochi sfide tris, forza4). Lo sfidato accetta con un
bottone che solo lui può premere; con la puntata le monete di entrambi vengono tolte all'accettazione
(partite aperte in core/repositories/partite_repo.py) e chiuse una per una a fine partita: prima chi perde,
poi chi vince, così un errore a metà non crea monete. Chi non muove entro 2 minuti perde.
Funzioni coperte: ECO-107, ECO-108, ECO-109
Dipende da: core/tavolo_logic.py
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from cogs.fun.sfide import SG_SFIDE
from core.command_groups import CogConGruppi, comando_di_gruppo, togli_comandi_del_cog
from core.database import db
from core.i18n import testo_per
from core.leveling_logic import controlla_puntata
from core.repositories.leveling_settings_repo import leveling_settings_repo
from core.repositories.partite_repo import EsitoApertura, partite_repo
from core.tavolo_logic import (
    COLONNE_F4, RIGHE_F4, SEGNI, SEGNI_TRIS, metti_f4, metti_tris, nuova_griglia, piena, testo_griglia,
    vincitore_f4, vincitore_tris,
)
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.tavolo")
NESSUNA_MENZIONE = discord.AllowedMentions.none()
POSTA_MASSIMA = 100_000


class TavoloView(BaseView):
    def __init__(self, gioco: str, guild_id: int, a: discord.Member, b: discord.Member, puntata: int, moneta: str) -> None:
        super().__init__(timeout=120)
        self.gioco, self.guild_id, self.giocatori, self.puntata, self.moneta = gioco, guild_id, {1: a, 2: b}, puntata, moneta
        self.turno = 1
        self.fase = "attesa"  # attesa -> in_corso -> fine
        self.griglia = nuova_griglia(3, 3) if gioco == "tris" else nuova_griglia(RIGHE_F4, COLONNE_F4)
        self.partite: dict[int, int] = {}
        self.messaggio: discord.Interaction | None = None
        self._costruisci_attesa()

    # ---------------------------------------------------------------- schermate
    def _costruisci_attesa(self) -> None:
        self.clear_items()
        for etichetta, stile, funzione in (("Accetta", discord.ButtonStyle.success, self._accetta), ("Rifiuta", discord.ButtonStyle.danger, self._rifiuta)):
            b = discord.ui.Button(label=etichetta, style=stile)
            b.callback = funzione
            self.add_item(b)

    def _costruisci_gioco(self) -> None:
        self.clear_items()
        if self.gioco == "tris":
            for r in range(3):
                for c in range(3):
                    b = discord.ui.Button(label="​" if not self.griglia[r][c] else SEGNI_TRIS[self.griglia[r][c]], row=r,
                                          style=discord.ButtonStyle.secondary, disabled=bool(self.griglia[r][c]))
                    b.callback = self._mossa_tris(r, c)
                    self.add_item(b)
        else:
            for c in range(COLONNE_F4):
                b = discord.ui.Button(label=str(c + 1), row=c // 4, style=discord.ButtonStyle.primary,
                                      disabled=self.griglia[0][c] != 0)
                b.callback = self._mossa_f4(c)
                self.add_item(b)

    def tavolo(self) -> str:
        segni = SEGNI_TRIS if self.gioco == "tris" else SEGNI
        a, b = self.giocatori[1], self.giocatori[2]
        posta = f" · posta {self.puntata} {self.moneta}" if self.puntata else ""
        return f"{segni[1]} {a.mention} contro {segni[2]} {b.mention}{posta}\n{testo_griglia(self.griglia, segni)}"

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
            for n in (1, 2):
                ap = await partite_repo.apri(self.guild_id, self.giocatori[n].id, self.gioco, self.puntata, attesa)
                if ap.esito is not EsitoApertura.APERTA:
                    for pid, utente in self.partite.items():  # restituisce quanto già tolto
                        await partite_repo.chiudi(pid, self.guild_id, utente, self.puntata)
                    self.fase = "fine"
                    self.stop()
                    chiave = "tav_non_puo" if ap.esito is not EsitoApertura.POCHE else "tav_poche"
                    await interaction.response.edit_message(
                        content=await testo_per(interaction, chiave, chi=self.giocatori[n].mention, moneta=self.moneta, pubblica=True),
                        view=None, allowed_mentions=NESSUNA_MENZIONE,
                    )
                    return
                self.partite[ap.partita_id] = self.giocatori[n].id
        self.fase = "in_corso"
        self._costruisci_gioco()
        await interaction.response.edit_message(content=self.tavolo() + f"\nTocca a {self.giocatori[self.turno].mention}", view=self,
                                                allowed_mentions=NESSUNA_MENZIONE)

    # ---------------------------------------------------------------- mosse
    def _mossa_tris(self, r: int, c: int):
        async def _cb(interaction: discord.Interaction) -> None:
            await self._gioca(interaction, lambda: metti_tris(self.griglia, r, c, self.turno))
        return _cb

    def _mossa_f4(self, c: int):
        async def _cb(interaction: discord.Interaction) -> None:
            await self._gioca(interaction, lambda: metti_f4(self.griglia, c, self.turno) is not None)
        return _cb

    async def _gioca(self, interaction: discord.Interaction, applica) -> None:
        if self.fase != "in_corso":
            await interaction.response.send_message(await testo_per(interaction, "leveling_gia_fatto"), ephemeral=True)
            return
        if interaction.user.id != self.giocatori[self.turno].id:
            await interaction.response.send_message(await testo_per(interaction, "tav_non_tuo_turno"), ephemeral=True)
            return
        if not applica():
            await interaction.response.send_message(await testo_per(interaction, "tav_mossa_no"), ephemeral=True)
            return
        vince = vincitore_tris(self.griglia) if self.gioco == "tris" else vincitore_f4(self.griglia)
        if vince:
            await self._fine(interaction, vince)
        elif piena(self.griglia):
            await self._fine(interaction, 0)
        else:
            self.turno = 3 - self.turno
            self._costruisci_gioco()
            await interaction.response.edit_message(content=self.tavolo() + f"\nTocca a {self.giocatori[self.turno].mention}", view=self,
                                                    allowed_mentions=NESSUNA_MENZIONE)

    async def _fine(self, interaction: discord.Interaction | None, vincitore: int, motivo: str = "") -> None:
        if self.fase == "fine":
            return
        self.fase = "fine"
        self.stop()
        if self.puntata and self.partite:
            ordine = sorted(self.partite.items(), key=lambda kv: kv[1] == (self.giocatori[vincitore].id if vincitore else 0))
            for pid, utente in ordine:  # prima chi perde (0), poi chi vince (doppio); pari: ognuno la sua
                ritorno = self.puntata if not vincitore else (self.puntata * 2 if utente == self.giocatori[vincitore].id else 0)
                try:
                    await partite_repo.chiudi(pid, self.guild_id, utente, ritorno)
                except Exception:
                    logger.exception("Chiusura della partita %s non riuscita", pid)
        for b in self.children:
            b.disabled = True
        origine = interaction or self.messaggio
        esito = f"🏆 Vince {self.giocatori[vincitore].mention}!" if vincitore else "🤝 Pareggio."
        testo = self.tavolo() + f"\n{esito} {motivo}"
        try:
            if interaction is not None:
                await interaction.response.edit_message(content=testo, view=self, allowed_mentions=NESSUNA_MENZIONE)
            elif origine is not None:
                await origine.edit_original_response(content=testo, view=self)
        except discord.HTTPException:
            pass

    async def on_timeout(self) -> None:
        if self.fase == "in_corso":
            await self._fine(None, 3 - self.turno, "(tempo scaduto)")  # chi non muove perde
        elif self.fase == "attesa":
            self.fase = "fine"


class TavoloCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def cog_unload(self) -> None:
        togli_comandi_del_cog(self)

    async def _sfida(self, interaction: discord.Interaction, gioco: str, membro: discord.Member, puntata: int) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return
        if membro.id == interaction.user.id or membro.bot:
            await interaction.response.send_message(await testo_per(interaction, "sfd_bersaglio"), ephemeral=True)
            return
        if puntata:
            for modulo in ("fun", "leveling"):
                if not await db.is_module_active_for_guild(guild.id, modulo):
                    await interaction.response.send_message(await testo_per(interaction, "ping_questo_modulo_non_attivo_su"), ephemeral=True)
                    return
        i = (await leveling_settings_repo.get_config(guild.id)).impostazioni
        if puntata:
            motivo = controlla_puntata(puntata, i)
            if motivo is not None:
                await interaction.response.send_message(f"❌ {motivo}", ephemeral=True)
                return
        view = TavoloView(gioco, guild.id, interaction.user, membro, puntata, i.currency_name)
        view.messaggio = interaction
        await interaction.response.send_message(
            await testo_per(interaction, "tav_sfida", sfidante=interaction.user.mention, sfidato=membro.mention, gioco=gioco, posta=puntata, moneta=i.currency_name, pubblica=True),
            view=view, allowed_mentions=discord.AllowedMentions(users=[membro]),
        )

    @comando_di_gruppo("giochi", nome="tris", descrizione="Tris contro un membro, anche con una puntata.", sottogruppo=SG_SFIDE)
    @app_commands.describe(membro="Chi sfidi", puntata="Monete in palio (0 = solo per divertimento)")
    async def tris(self, interaction: discord.Interaction, membro: discord.Member, puntata: app_commands.Range[int, 0, POSTA_MASSIMA] = 0) -> None:
        await self._sfida(interaction, "tris", membro, puntata)

    @comando_di_gruppo("giochi", nome="forza4", descrizione="Forza 4 contro un membro, anche con una puntata.", sottogruppo=SG_SFIDE)
    @app_commands.describe(membro="Chi sfidi", puntata="Monete in palio (0 = solo per divertimento)")
    async def forza4(self, interaction: discord.Interaction, membro: discord.Member, puntata: app_commands.Range[int, 0, POSTA_MASSIMA] = 0) -> None:
        await self._sfida(interaction, "forza4", membro, puntata)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TavoloCog(bot))
