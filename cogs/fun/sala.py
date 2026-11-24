"""
cogs/fun/sala.py
================
Giochi a più giocatori con sala d'attesa (/sala ...): roulette, corsa di animali, lotta, bomba, carte a turni e bingo
con la puntata di tutti; impiccato e quiz con un piccolo premio e un tetto al giorno. La puntata si toglie a tutti
insieme, in una sola transazione, quando la partita parte (partite_repo.apri_gruppo): se la partita non parte non si
è pagato niente, e se il bot si ferma le puntate rimaste tornano indietro all'avvio. Solo i giocatori della sala
agiscono. Le monete dei giochi non si comprano con soldi veri.
Funzioni coperte: ECO-091, ECO-093, ECO-101, ECO-102, ECO-103, ECO-105, ECO-110, ECO-111, ECO-112, ECO-113, ECO-114
Dipende da: core/sala_logic.py, core/combattimento_logic.py, cogs/fun/_combattimento.py, cogs/fun/_lobby.py, core/repositories/partite_repo.py
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from types import SimpleNamespace
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from cogs.fun._combattimento import gioca_combattimento
from cogs.fun._lobby import apri_lobby
from core import combattimento_logic as cb
from core import sala_logic as sl
from core.animali_logic import livello as livello_animale, salute as salute_animale
from core.command_groups import CogConGruppi, comando_di_gruppo, togli_comandi_del_cog
from core.database import db
from core.i18n import testo_per
from core.leveling_logic import controlla_puntata
from core.repositories.animali_repo import animali_repo
from core.repositories.contenuti_repo import contenuti_repo
from core.repositories.leveling_settings_repo import leveling_settings_repo
from core.repositories.partite_repo import EsitoApertura, partite_repo
from core.repositories.sociale_repo import sociale_repo
from core.ui_base import BaseModal, BaseView

logger = logging.getLogger("iyokai.sala")
NESSUNA_MENZIONE = discord.AllowedMentions.none()
RNG = random.SystemRandom()
SECONDI_LOBBY = 45
PUNTATA_TETTO = 1_000_000
DURATA_MASSIMA = 11 * 60  # le righe delle puntate scadono dopo 15 minuti: nessuna partita va oltre
SECONDI_TURNO = 30
PREMIO_RISPOSTA = 10
PREMIO_IMPICCATO = 20
TETTO_PREMI_GIORNO = 300
PREFISSO = "sala:"

SCELTE_ROULETTE = [k for k in ("rosso", "nero", "pari", "dispari", "basso", "alto", "dozzina1", "dozzina2", "dozzina3", "colonna1", "colonna2", "colonna3")]


class VistaGiocatori(BaseView):
    """Una vista che solo i giocatori della sala possono usare."""

    def __init__(self, giocatori: list[int], secondi: float) -> None:
        super().__init__(timeout=secondi)
        self.giocatori = set(giocatori)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        if interaction.user.id not in self.giocatori:
            await interaction.response.send_message(await testo_per(interaction, "sala_non_giochi"), ephemeral=True)
            return False
        return True


class Tavolo:
    """Chi gioca, quanto si punta e come si scrive nel canale. Il testo passa sempre da testo_per."""

    def __init__(self, interaction: discord.Interaction, giocatori: list[int], puntata: int, moneta: str) -> None:
        self.interaction, self.giocatori, self.puntata, self.moneta = interaction, giocatori, puntata, moneta
        self.fine_at = time.monotonic() + DURATA_MASSIMA
        self.rng = RNG
        self.regole: SimpleNamespace | None = None  # solo i giochi con regole su misura (combattimento)

    async def t(self, chiave: str, **kw) -> str:
        return await testo_per(self.interaction, chiave, pubblica=True, **kw)

    async def invia(self, contenuto: str, view: discord.ui.View | None = None) -> discord.WebhookMessage:
        return await self.interaction.followup.send(
            contenuto[:2000], view=view if view is not None else discord.utils.MISSING, allowed_mentions=NESSUNA_MENZIONE, wait=True
        )

    @staticmethod
    async def modifica(messaggio: discord.WebhookMessage, contenuto: str, view: discord.ui.View | None = None) -> None:
        try:
            await messaggio.edit(content=contenuto[:2000], view=view, allowed_mentions=NESSUNA_MENZIONE)
        except discord.HTTPException:
            pass

    def scaduto(self) -> bool:
        return time.monotonic() > self.fine_at

    def menzioni(self, utenti) -> str:
        return " ".join(f"<@{u}>" for u in utenti)

    @property
    def piatto(self) -> int:
        return self.puntata * len(self.giocatori)


def rimborso(giocatori: list[int], puntata: int) -> dict[int, int]:
    return {u: puntata for u in giocatori}


def vince_il_piatto(giocatori: list[int], puntata: int, vincitore: int) -> dict[int, int]:
    """Il piatto intero al vincitore, gli altri 0: la somma resta uguale a quanto è stato puntato."""
    return {u: (puntata * len(giocatori) if u == vincitore else 0) for u in giocatori}


# ============================================================== roulette (ECO-091)
class ModaleNumero(BaseModal):
    def __init__(self, vista: "VistaRoulette", titolo: str, etichetta: str) -> None:
        super().__init__(title=titolo[:45])
        self.vista = vista
        self.numero = discord.ui.TextInput(label=etichetta[:45], min_length=1, max_length=2, required=True)
        self.add_item(self.numero)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        testo = self.numero.value.strip()
        if not testo.isascii() or not testo.isdigit() or not 0 <= int(testo) <= 36:
            await interaction.response.send_message(await testo_per(interaction, "sala_rou_numero_no"), ephemeral=True)
            return
        await self.vista.scegli(interaction, "numero", int(testo))


class VistaRoulette(VistaGiocatori):
    def __init__(self, giocatori: list[int], secondi: float, etichette: dict[str, str], testi: dict[str, str]) -> None:
        super().__init__(giocatori, secondi)
        self.scelte: dict[int, tuple[str, int | None]] = {}
        self.completa = asyncio.Event()
        self.testi = testi
        self.scommessa.options = [discord.SelectOption(label=etichette[k][:100], value=k) for k in SCELTE_ROULETTE]
        self.scommessa.placeholder = testi["segnaposto"][:100]
        self.numero.label = testi["numero"][:45]

    async def scegli(self, interaction: discord.Interaction, scelta: str, numero: int | None) -> None:
        self.scelte[interaction.user.id] = (scelta, numero)  # l'ultima scelta vale
        await interaction.response.send_message(await testo_per(interaction, "sala_rou_scelto"), ephemeral=True)
        if len(self.scelte) >= len(self.giocatori):
            self.completa.set()

    @discord.ui.select(placeholder="…", options=[discord.SelectOption(label="x", value="x")])
    async def scommessa(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
        await self.scegli(interaction, select.values[0], None)

    @discord.ui.button(style=discord.ButtonStyle.secondary, label="…")
    async def numero(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(ModaleNumero(self, self.testi["numero"], self.testi["numero_campo"]))


async def gioca_roulette(tv: Tavolo) -> dict[int, int]:
    etichette = {k: await tv.t(f"sala_rou_{k}") for k in SCELTE_ROULETTE}
    testi = {"segnaposto": await tv.t("sala_rou_segnaposto"), "numero": await tv.t("sala_rou_numero"), "numero_campo": await tv.t("sala_rou_numero_campo")}
    vista = VistaRoulette(tv.giocatori, 40, etichette, testi)
    msg = await tv.invia(await tv.t("sala_rou_tavolo", secondi=30, piatto=tv.piatto, moneta=tv.moneta), vista)
    try:
        await asyncio.wait_for(vista.completa.wait(), 30)
    except asyncio.TimeoutError:
        pass
    vista.stop()
    scelte = dict(vista.scelte)
    if not scelte:
        await tv.modifica(msg, await tv.t("sala_nessuna_mossa"))
        return rimborso(tv.giocatori, tv.puntata)
    uscito, pagamenti = sl.risolvi_roulette(scelte, tv.puntata, tv.rng)
    risultato = {u: pagamenti.get(u, tv.puntata if u not in scelte else 0) for u in tv.giocatori}  # chi non ha scelto riprende la puntata
    righe = [f"<@{u}>: " + (f"+{risultato[u] - tv.puntata}" if risultato[u] > tv.puntata else (f"{risultato[u] - tv.puntata}" if u in scelte else "=")) for u in tv.giocatori]
    await tv.modifica(msg, await tv.t("sala_rou_esito", uscito=uscito, righe="\n".join(righe), moneta=tv.moneta))
    return risultato


# ============================================================== corsa (ECO-102, ECO-103) e lotta (ECO-101, ECO-105)
async def _animale_principale(guild_id: int, user_id: int):
    righe = await animali_repo.elenco(guild_id, user_id)
    if not righe:
        return None
    adesso = datetime.now(timezone.utc)
    migliore = max(righe, key=lambda r: (livello_animale(r["xp"]), r["id"]))
    return livello_animale(migliore["xp"]), salute_animale(migliore["fame_at"], migliore["igiene_at"], migliore["gioco_at"], adesso) >= 30, migliore["nome"]


async def gioca_corsa(tv: Tavolo) -> dict[int, int]:
    guild_id = tv.interaction.guild.id
    velocita, nomi = {}, {}
    for u in tv.giocatori:
        a = await _animale_principale(guild_id, u)
        velocita[u] = sl.velocita_animale(a[0], a[1]) if a else 1.0
        nomi[u] = a[2] if a else await tv.t("sala_spirito")
    vincitore, storia = sl.corsa(velocita, tv.rng)
    msg = await tv.invia(await tv.t("sala_corsa_via", piatto=tv.piatto, moneta=tv.moneta))
    passi = storia[:: max(1, len(storia) // 6)]
    if passi[-1] is not storia[-1]:
        passi.append(storia[-1])
    for pos in passi:
        await asyncio.sleep(2)
        piste = "\n".join(f"`{min(int(pos[u] / sl.LUNGHEZZA_CORSA * 20), 20):>2}` {'▬' * min(int(pos[u] / sl.LUNGHEZZA_CORSA * 20), 20)}🐾 {nomi[u][:20]} <@{u}>" for u in tv.giocatori)
        await tv.modifica(msg, await tv.t("sala_corsa_pista", piste=piste))
    await tv.modifica(msg, await tv.t("sala_corsa_fine", vincitore=f"<@{vincitore}>", nome=nomi[vincitore][:20], piatto=tv.piatto, moneta=tv.moneta))
    return vince_il_piatto(tv.giocatori, tv.puntata, vincitore)


async def gioca_lotta(tv: Tavolo) -> dict[int, int]:
    guild_id = tv.interaction.guild.id
    forza, nomi = {}, {}
    for u in tv.giocatori:
        a = await _animale_principale(guild_id, u)
        forza[u] = sl.forza_lottatore(a[0] if a else None)
        nomi[u] = a[2] if a else await tv.t("sala_spirito")
    vincitore, eliminati = sl.lotta(forza, tv.rng)
    msg = await tv.invia(await tv.t("sala_lotta_via", elenco="\n".join(f"{nomi[u][:20]} (<@{u}>) {forza[u]}%" for u in tv.giocatori)))
    fuori = []
    for u in eliminati:
        await asyncio.sleep(2)
        fuori.append(f"💥 {nomi[u][:20]} (<@{u}>)")
        await tv.modifica(msg, await tv.t("sala_lotta_giro", fuori="\n".join(fuori)))
    await asyncio.sleep(1)
    await tv.modifica(msg, await tv.t("sala_lotta_fine", fuori="\n".join(fuori), vincitore=f"<@{vincitore}>", nome=nomi[vincitore][:20], piatto=tv.piatto, moneta=tv.moneta))
    return vince_il_piatto(tv.giocatori, tv.puntata, vincitore)


# ============================================================== bomba (ECO-110)
class VistaBomba(VistaGiocatori):
    def __init__(self, bomba: sl.Bomba, giocatori: list[int]) -> None:
        super().__init__(giocatori, DURATA_MASSIMA)
        self.bomba = bomba
        self.ultima_mossa = time.monotonic()
        self.cambiata = asyncio.Event()
        self.ultimo_testo = ""
        self.ricostruisci()

    def ricostruisci(self) -> None:
        self.clear_items()
        for filo in self.bomba.fili:
            b = discord.ui.Button(label="✂", emoji=sl.COLORI_FILI[filo], style=discord.ButtonStyle.secondary, row=filo // 5)
            b.callback = self._taglia(filo)
            self.add_item(b)

    def _taglia(self, filo: int):
        async def callback(interaction: discord.Interaction) -> None:
            esito = self.bomba.taglia(interaction.user.id, filo)  # nessun await tra il controllo del turno e la mossa
            if esito == "non_turno":
                await interaction.response.send_message(await testo_per(interaction, "sala_non_tuo_turno"), ephemeral=True)
                return
            if esito == "filo_no":
                await interaction.response.send_message(await testo_per(interaction, "sala_filo_no"), ephemeral=True)
                return
            self.ultima_mossa = time.monotonic()
            chiave = {"salvo": "sala_bomba_salvo", "esplode": "sala_bomba_esplode", "vince": "sala_bomba_esplode"}[esito]
            self.ultimo_testo = await testo_per(interaction, chiave, pubblica=True, chi=f"<@{interaction.user.id}>")
            self.ricostruisci()
            if esito == "vince":
                self.stop()
            await interaction.response.edit_message(content=await self._testo(interaction), view=None if esito == "vince" else self, allowed_mentions=NESSUNA_MENZIONE)
            self.cambiata.set()
        return callback

    async def _testo(self, interaction) -> str:
        if self.bomba.vincitore is not None:
            return f"{self.ultimo_testo}\n" + await testo_per(interaction, "sala_bomba_vince", pubblica=True, chi=f"<@{self.bomba.vincitore}>")
        vivi = " ".join(f"<@{u}>" for u in self.bomba.vivi)
        return f"{self.ultimo_testo}\n" + await testo_per(
            interaction, "sala_bomba_turno", pubblica=True, chi=f"<@{self.bomba.di_turno}>", vivi=vivi, secondi=SECONDI_TURNO, fili=len(self.bomba.fili)
        )


async def gioca_bomba(tv: Tavolo) -> dict[int, int]:
    bomba = sl.Bomba(list(tv.giocatori), tv.rng)
    vista = VistaBomba(bomba, tv.giocatori)
    msg = await tv.invia(await vista._testo(tv.interaction), vista)
    while bomba.vincitore is None and not tv.scaduto():
        await asyncio.sleep(1)
        if time.monotonic() - vista.ultima_mossa > SECONDI_TURNO:
            lento = bomba.di_turno
            bomba.esci(lento)
            vista.ultima_mossa = time.monotonic()
            vista.ultimo_testo = await tv.t("sala_lento", chi=f"<@{lento}>")
            vista.ricostruisci()
            if bomba.vincitore is not None:
                vista.stop()
            await tv.modifica(msg, await vista._testo(tv.interaction), None if bomba.vincitore is not None else vista)
    vista.stop()
    if bomba.vincitore is None:
        await tv.modifica(msg, await tv.t("sala_tempo_finito"))
        return rimborso(tv.giocatori, tv.puntata)
    return vince_il_piatto(tv.giocatori, tv.puntata, bomba.vincitore)


# ============================================================== tamburo (ECO-093)
class VistaTamburo(VistaGiocatori):
    """Un solo bottone: preme la prossima casella chi ha il turno. Nome e testi neutri: una sfera rossa in un tamburo."""

    def __init__(self, tamburo: sl.Tamburo, giocatori: list[int]) -> None:
        super().__init__(giocatori, DURATA_MASSIMA)
        self.tamburo = tamburo
        self.ultima_mossa = time.monotonic()
        self.ultimo_testo = ""

    @discord.ui.button(label="🎯", style=discord.ButtonStyle.primary)
    async def premi(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        esito = self.tamburo.premi(interaction.user.id)  # nessun await tra il controllo del turno e la mossa
        if esito == "non_turno":
            await interaction.response.send_message(await testo_per(interaction, "sala_non_tuo_turno"), ephemeral=True)
            return
        self.ultima_mossa = time.monotonic()
        chiave = {"salvo": "sala_tamburo_salvo", "fuori": "sala_tamburo_fuori", "vince": "sala_tamburo_fuori"}[esito]
        self.ultimo_testo = await testo_per(interaction, chiave, pubblica=True, chi=f"<@{interaction.user.id}>")
        if esito == "vince":
            self.stop()
        await interaction.response.edit_message(content=await self._testo(interaction), view=None if esito == "vince" else self, allowed_mentions=NESSUNA_MENZIONE)

    async def _testo(self, interaction) -> str:
        if self.tamburo.vincitore is not None:
            return f"{self.ultimo_testo}\n" + await testo_per(interaction, "sala_tamburo_vince", pubblica=True, chi=f"<@{self.tamburo.vincitore}>")
        vivi = " ".join(f"<@{u}>" for u in self.tamburo.vivi)
        caselle = "🔘" * self.tamburo.posizione + "⚪" * (sl.Tamburo.CASELLE - self.tamburo.posizione)
        return f"{self.ultimo_testo}\n" + await testo_per(
            interaction, "sala_tamburo_turno", pubblica=True, chi=f"<@{self.tamburo.di_turno}>", vivi=vivi, secondi=SECONDI_TURNO, caselle=caselle
        )


async def gioca_tamburo(tv: Tavolo) -> dict[int, int]:
    tamburo = sl.Tamburo(list(tv.giocatori), tv.rng)
    vista = VistaTamburo(tamburo, tv.giocatori)
    msg = await tv.invia(await vista._testo(tv.interaction), vista)
    while tamburo.vincitore is None and not tv.scaduto():
        await asyncio.sleep(1)
        if time.monotonic() - vista.ultima_mossa > SECONDI_TURNO:
            lento = tamburo.di_turno
            tamburo.esci(lento)
            vista.ultima_mossa = time.monotonic()
            vista.ultimo_testo = await tv.t("sala_lento", chi=f"<@{lento}>")
            if tamburo.vincitore is not None:
                vista.stop()
            await tv.modifica(msg, await vista._testo(tv.interaction), None if tamburo.vincitore is not None else vista)
    vista.stop()
    if tamburo.vincitore is None:
        await tv.modifica(msg, await tv.t("sala_tempo_finito"))
        return rimborso(tv.giocatori, tv.puntata)
    return vince_il_piatto(tv.giocatori, tv.puntata, tamburo.vincitore)


# ============================================================== carte a turni (ECO-111)
class SceltaCarta(discord.ui.Select):
    def __init__(self, vista: "VistaCarte", utente: int, segnaposto: str) -> None:
        mano = vista.partita.mani[utente]
        cima = vista.partita.cima
        opzioni = [discord.SelectOption(label=sl.nome_carta(c), value=str(i)) for i, c in enumerate(mano) if sl.giocabile(c, cima)][:25]
        super().__init__(placeholder=segnaposto[:100], options=opzioni)
        self.vista = vista

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.vista.gioca(interaction, int(self.values[0]))


class VistaCarte(VistaGiocatori):
    def __init__(self, partita: sl.PartitaCarte, giocatori: list[int], etichette: dict[str, str]) -> None:
        super().__init__(giocatori, DURATA_MASSIMA)
        self.partita, self.etichette = partita, etichette
        self.ultima_mossa = time.monotonic()
        self.ultimo_testo = ""
        self.da_aggiornare = asyncio.Event()
        self.mano_btn.label, self.pesca_btn.label = etichette["mano_b"][:45], etichette["pesca"][:45]

    async def testo(self, interaction) -> str:
        p = self.partita
        if p.vincitore is not None:
            return f"{self.ultimo_testo}\n" + await testo_per(interaction, "sala_carte_vince", pubblica=True, chi=f"<@{p.vincitore}>")
        conteggi = " · ".join(f"<@{u}> {len(p.mani[u])}" for u in p.ordine)
        return f"{self.ultimo_testo}\n" + await testo_per(
            interaction, "sala_carte_tavolo", pubblica=True, cima=sl.nome_carta(p.cima), chi=f"<@{p.di_turno}>", conteggi=conteggi, secondi=SECONDI_TURNO
        )

    async def gioca(self, interaction: discord.Interaction, indice: int) -> None:
        esito = self.partita.gioca(interaction.user.id, indice)
        if esito in ("non_turno", "non_valida"):
            await interaction.response.send_message(await testo_per(interaction, "sala_non_tuo_turno" if esito == "non_turno" else "sala_carta_no"), ephemeral=True)
            return
        self.ultima_mossa = time.monotonic()
        self.ultimo_testo = await testo_per(interaction, "sala_carte_giocata", pubblica=True, chi=f"<@{interaction.user.id}>", carta=sl.nome_carta(self.partita.cima))
        await interaction.response.edit_message(content=await testo_per(interaction, "sala_carte_fatto"), view=None)  # chiude il messaggio privato
        if esito == "vince":
            self.stop()
        self.da_aggiornare.set()  # il giro principale riscrive il tavolo

    @discord.ui.button(style=discord.ButtonStyle.primary, label="…")
    async def mano_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        mano = self.partita.mani.get(interaction.user.id)
        if mano is None:
            await interaction.response.send_message(await testo_per(interaction, "sala_non_giochi"), ephemeral=True)
            return
        testo = await testo_per(interaction, "sala_carte_mano", mano=" ".join(sl.nome_carta(c) for c in mano), cima=sl.nome_carta(self.partita.cima))
        vista = BaseView(timeout=SECONDI_TURNO)
        if self.partita.di_turno == interaction.user.id:
            vista.add_item(SceltaCarta(self, interaction.user.id, self.etichette["gioca"]))
        if not vista.children:
            vista = discord.utils.MISSING
        await interaction.response.send_message(testo, view=vista, ephemeral=True)

    @discord.ui.button(style=discord.ButtonStyle.secondary, label="…")
    async def pesca_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.partita.di_turno != interaction.user.id:
            await interaction.response.send_message(await testo_per(interaction, "sala_non_tuo_turno"), ephemeral=True)
            return
        self.partita.pesca(interaction.user.id)
        self.ultima_mossa = time.monotonic()
        self.ultimo_testo = await testo_per(interaction, "sala_carte_pescata", pubblica=True, chi=f"<@{interaction.user.id}>")
        await interaction.response.edit_message(content=await self.testo(interaction), view=self, allowed_mentions=NESSUNA_MENZIONE)


async def gioca_carte(tv: Tavolo) -> dict[int, int]:
    partita = sl.PartitaCarte(list(tv.giocatori), tv.rng)
    etichette = {k: await tv.t(f"sala_carte_{k}") for k in ("mano_b", "pesca", "gioca")}
    vista = VistaCarte(partita, tv.giocatori, etichette)
    msg = await tv.invia(await vista.testo(tv.interaction), vista)
    while partita.vincitore is None and not tv.scaduto():
        await asyncio.sleep(1)
        if vista.da_aggiornare.is_set():
            vista.da_aggiornare.clear()
            await tv.modifica(msg, await vista.testo(tv.interaction), vista)
        if time.monotonic() - vista.ultima_mossa > SECONDI_TURNO:
            lento = partita.di_turno
            partita.esci(lento)
            vista.ultima_mossa = time.monotonic()
            vista.ultimo_testo = await tv.t("sala_lento", chi=f"<@{lento}>")
            if partita.vincitore is not None:
                vista.stop()
            await tv.modifica(msg, await vista.testo(tv.interaction), None if partita.vincitore is not None else vista)
    vista.stop()
    if partita.vincitore is None:
        await tv.modifica(msg, await tv.t("sala_tempo_finito"))
        return rimborso(tv.giocatori, tv.puntata)
    await tv.modifica(msg, await vista.testo(tv.interaction), None)
    return vince_il_piatto(tv.giocatori, tv.puntata, partita.vincitore)


# ============================================================== bingo (ECO-112)
class VistaBingo(VistaGiocatori):
    def __init__(self, giocatori: list[int], cartelle: dict[int, list[list[int]]], etichette: dict[str, str]) -> None:
        super().__init__(giocatori, DURATA_MASSIMA)
        self.cartelle, self.estratti = cartelle, set()
        self.vincitore: int | None = None
        self.vista_cartella.label, self.bingo.label = etichette["cartella"][:45], etichette["bingo"][:45]

    @discord.ui.button(style=discord.ButtonStyle.secondary, label="…")
    async def vista_cartella(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        c = self.cartelle[interaction.user.id]
        await interaction.response.send_message(f"```\n{sl.testo_cartella(c, self.estratti)}\n```", ephemeral=True)

    @discord.ui.button(style=discord.ButtonStyle.success, label="…")
    async def bingo(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.vincitore is None and sl.ha_bingo(self.cartelle[interaction.user.id], self.estratti):
            self.vincitore = interaction.user.id  # nessun await tra il controllo e il segno: vince il primo
            self.stop()
            await interaction.response.send_message(await testo_per(interaction, "sala_bingo_tuo"), ephemeral=True)
        elif self.vincitore is not None:
            await interaction.response.send_message(await testo_per(interaction, "sala_bingo_tardi"), ephemeral=True)
        else:
            await interaction.response.send_message(await testo_per(interaction, "sala_bingo_no"), ephemeral=True)


async def gioca_bingo(tv: Tavolo) -> dict[int, int]:
    cartelle = {u: sl.cartella_bingo(tv.rng) for u in tv.giocatori}
    etichette = {k: await tv.t(f"sala_bingo_{k}") for k in ("cartella", "bingo")}
    vista = VistaBingo(tv.giocatori, cartelle, etichette)
    msg = await tv.invia(await tv.t("sala_bingo_via", piatto=tv.piatto, moneta=tv.moneta), vista)
    for n in sl.ordine_estrazione(tv.rng):
        if vista.vincitore is not None or tv.scaduto():
            break
        await asyncio.sleep(4)
        if vista.vincitore is not None:
            break
        vista.estratti.add(n)
        recenti = " ".join(str(x) for x in sorted(vista.estratti))
        await tv.modifica(msg, await tv.t("sala_bingo_numero", n=n, usciti=recenti), vista)
    await asyncio.sleep(1)
    vista.stop()
    if vista.vincitore is None:
        await tv.modifica(msg, await tv.t("sala_bingo_nessuno"), None)
        return rimborso(tv.giocatori, tv.puntata)
    await tv.modifica(msg, await tv.t("sala_bingo_vince", chi=f"<@{vista.vincitore}>", piatto=tv.piatto, moneta=tv.moneta), None)
    return vince_il_piatto(tv.giocatori, tv.puntata, vincitore=vista.vincitore)


MOTORI = {
    "roulette": ("sala:roulette", gioca_roulette, 2, 10),
    "corsa": ("sala:corsa", gioca_corsa, 2, 10),
    "lotta": ("sala:lotta", gioca_lotta, 2, 6),
    "combattimento": ("sala:combattimento", gioca_combattimento, cb.MIN_GIOCATORI, cb.MAX_GIOCATORI),  # ECO-105
    "bomba": ("sala:bomba", gioca_bomba, 2, 10),
    "tamburo": ("sala:tamburo", gioca_tamburo, 2, 10),  # ECO-093
    "carte": ("sala:carte", gioca_carte, 2, 6),
    "bingo": ("sala:bingo", gioca_bingo, 2, 10),
}


# ============================================================== impiccato (ECO-113) e quiz (ECO-114)
class VistaLettere(VistaGiocatori):
    def __init__(self, giocatori: list[int], gioco: sl.Impiccato, segnaposto: str) -> None:
        super().__init__(giocatori, DURATA_MASSIMA)
        self.gioco = gioco
        self.cambiata = asyncio.Event()
        self.ultimo = ""
        for meta, lettere in enumerate((sl.ALFABETO[:13], sl.ALFABETO[13:])):
            s = discord.ui.Select(placeholder=f"{segnaposto} {lettere[0]}-{lettere[-1]}"[:100], options=[discord.SelectOption(label=c, value=c) for c in lettere], row=meta)
            s.callback = self._scelta(s)
            self.add_item(s)

    def _scelta(self, select: discord.ui.Select):
        async def callback(interaction: discord.Interaction) -> None:
            esito = self.gioco.prova(select.values[0])
            self.ultimo = f"{interaction.user.display_name[:30]}: {select.values[0]} → {esito}"
            await interaction.response.defer()
            self.cambiata.set()
        return callback


def disegno_impiccato(errori: int) -> str:
    parti = ["😵", "👕", "💪", "💪", "🦵", "🦵"]
    return "".join(parti[:errori]) or "·"


async def gioca_impiccato(tv: Tavolo) -> dict[int, int]:
    gioco = sl.Impiccato(tv.rng.choice(sl.parole_impiccato()))
    vista = VistaLettere(tv.giocatori, gioco, await tv.t("sala_imp_segnaposto"))

    async def testo() -> str:
        return await tv.t(
            "sala_imp_tavolo", parola=gioco.mascherata, errori=len(gioco.sbagliate), massimo=sl.ERRORI_MASSIMI,
            sbagliate=" ".join(gioco.sbagliate) or "-", disegno=disegno_impiccato(len(gioco.sbagliate)), ultimo=vista.ultimo,
        )
    msg = await tv.invia(await testo(), vista)
    ultimo = time.monotonic()
    while not gioco.finita and not tv.scaduto():
        try:
            await asyncio.wait_for(vista.cambiata.wait(), 20)
        except asyncio.TimeoutError:
            if time.monotonic() - ultimo > 120:
                break  # nessuno gioca da due minuti
            continue
        ultimo = time.monotonic()
        vista.cambiata.clear()
        await tv.modifica(msg, await testo(), None if gioco.finita else vista)
    vista.stop()
    if not gioco.vinta:
        await tv.modifica(msg, await tv.t("sala_imp_perso", parola=gioco.parola), None)
        return {}
    premiati = []
    for u in tv.giocatori:
        dato = await contenuti_repo.premia(tv.interaction.guild.id, u, "impiccato", PREMIO_IMPICCATO, TETTO_PREMI_GIORNO)
        if dato:
            premiati.append(f"<@{u}> +{dato}")
    await tv.modifica(msg, await tv.t("sala_imp_vinto", parola=gioco.parola, premi=" ".join(premiati) or "-", moneta=tv.moneta), None)
    return {}


class VistaRisposte(VistaGiocatori):
    def __init__(self, giocatori: list[int], domanda: dict) -> None:
        super().__init__(giocatori, 40)
        self.domanda = domanda
        self.risposte: dict[int, int] = {}
        self.completa = asyncio.Event()
        for i, r in enumerate(domanda["r"]):
            b = discord.ui.Button(label=f"{'ABCD'[i]}: {r}"[:80], style=discord.ButtonStyle.primary)
            b.callback = self._rispondi(i)
            self.add_item(b)

    def _rispondi(self, indice: int):
        async def callback(interaction: discord.Interaction) -> None:
            if interaction.user.id in self.risposte:  # una sola risposta, nessun await prima del segno
                await interaction.response.send_message(await testo_per(interaction, "sala_quiz_gia"), ephemeral=True)
                return
            self.risposte[interaction.user.id] = indice
            await interaction.response.send_message(await testo_per(interaction, "sala_quiz_ricevuta"), ephemeral=True)
            if len(self.risposte) >= len(self.giocatori):
                self.completa.set()
        return callback


async def gioca_quiz(tv: Tavolo) -> dict[int, int]:
    punti = {u: 0 for u in tv.giocatori}
    for n, d in enumerate(sl.scegli_domande(tv.rng), 1):
        vista = VistaRisposte(tv.giocatori, d)
        msg = await tv.invia(await tv.t("sala_quiz_domanda", n=n, tot=sl.DOMANDE_PER_PARTITA, domanda=d["d"], secondi=15, categoria=d["c"]), vista)
        try:
            await asyncio.wait_for(vista.completa.wait(), 15)
        except asyncio.TimeoutError:
            pass
        vista.stop()
        giusti = [u for u, r in vista.risposte.items() if r == d["g"]]
        for u in giusti:
            punti[u] += 1
        await tv.modifica(msg, await tv.t("sala_quiz_risposta", domanda=d["d"], giusta=f"{'ABCD'[d['g']]}: {d['r'][d['g']]}", giusti=tv.menzioni(giusti) or "-"), None)
    premiati = []
    for u, p in punti.items():
        if p:
            dato = await contenuti_repo.premia(tv.interaction.guild.id, u, "quiz", PREMIO_RISPOSTA * p, TETTO_PREMI_GIORNO)
            premiati.append(f"<@{u}>: {p}/{sl.DOMANDE_PER_PARTITA} (+{dato})")
    await tv.invia(await tv.t("sala_quiz_fine", classifica="\n".join(premiati) or "-", moneta=tv.moneta))
    return {}


# ============================================================== il comando e la sala
class SalaCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._occupati: set[tuple[int, int]] = set()  # (server, canale): una partita per canale
        self._rimborsi.start()

    def cog_unload(self) -> None:
        self._rimborsi.cancel()
        togli_comandi_del_cog(self)

    @tasks.loop(minutes=5)
    async def _rimborsi(self) -> None:
        try:
            await partite_repo.rimborsa_scadute()
        except Exception:
            logger.exception("Giro dei rimborsi delle sale")

    @_rimborsi.before_loop
    async def _prima(self) -> None:
        await self.bot.wait_until_ready()
        try:  # all'avvio: le partite a più giocatori stanno in memoria, quelle rimaste aperte sono perse e si rimborsano
            await partite_repo.rimborsa_gioco(PREFISSO)
        except Exception:
            logger.exception("Rimborso delle sale all'avvio")

    async def _attivo(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return False
        for modulo in ("fun", "leveling"):
            if not await db.is_module_active_for_guild(interaction.guild.id, modulo):
                await interaction.response.send_message(await testo_per(interaction, "ping_questo_modulo_non_attivo_su"), ephemeral=True)
                return False
        return True

    @staticmethod
    def _verifica_ingresso(host_id: int):
        async def verifica(interaction: discord.Interaction) -> str | None:
            """Il blocco personale (ECO-155): niente sala con chi ti ha bloccato o con chi hai bloccato."""
            if await sociale_repo.ha_bloccato(host_id, interaction.user.id) or await sociale_repo.ha_bloccato(interaction.user.id, host_id):
                return "soc_bloccato"
            return None
        return verifica

    async def _partita(self, interaction: discord.Interaction, nome: str, puntata: int, regole: SimpleNamespace | None = None) -> None:
        if not await self._attivo(interaction):
            return
        guild, canale = interaction.guild, interaction.channel
        gioco, motore, minimo, massimo = MOTORI[nome]
        impostazioni = (await leveling_settings_repo.get_config(guild.id)).impostazioni
        motivo = controlla_puntata(puntata, impostazioni)
        if motivo is not None:
            await interaction.response.send_message(f"❌ {motivo}", ephemeral=True)
            return
        chiave = (guild.id, getattr(canale, "id", 0))
        if chiave in self._occupati:
            await interaction.response.send_message(await testo_per(interaction, "sala_canale_occupato"), ephemeral=True)
            return
        self._occupati.add(chiave)
        try:
            await interaction.response.defer()
            intro, extra = "sala_intro", {}
            if regole is not None:  # ECO-105: le regole scelte da chi crea si mostrano nella sala d'attesa
                intro = "sala_comb_intro"
                extra = {
                    "vite": regole.vite, "giri": regole.giri,
                    "oggetti": await testo_per(interaction, "cmb_si" if regole.oggetti else "cmb_no", pubblica=True),
                }
            giocatori = await apri_lobby(
                interaction, minimo, massimo, intro, SECONDI_LOBBY, verifica=self._verifica_ingresso(interaction.user.id),
                gioco=await testo_per(interaction, f"sala_nome_{nome}", pubblica=True), puntata=puntata, moneta=impostazioni.currency_name,
                **extra,
            )
            if giocatori is None:
                await interaction.followup.send(await testo_per(interaction, "sala_non_parte", pubblica=True))
                return
            giocatori = await self._blocca_puntate(interaction, gioco, giocatori, minimo, puntata, impostazioni)
            if giocatori is None:
                return
            tavolo = Tavolo(interaction, giocatori, puntata, impostazioni.currency_name)
            tavolo.regole = regole
            try:
                restituzioni = await motore(tavolo)
            except Exception:
                logger.exception("Partita %s in errore: puntate restituite", nome)
                restituzioni = rimborso(giocatori, puntata)
            try:
                await partite_repo.chiudi_gruppo(guild.id, gioco, restituzioni or rimborso(giocatori, puntata))
            except Exception:
                logger.exception("Chiusura della partita %s non riuscita: le puntate tornano allo scadere", nome)
        finally:
            self._occupati.discard(chiave)

    async def _blocca_puntate(self, interaction, gioco, giocatori, minimo, puntata, impostazioni) -> list[int] | None:
        """Toglie la puntata a tutti insieme. Chi non può (pochi soldi, pausa, già in una partita) esce dalla sala."""
        guild = interaction.guild
        esclusi = []
        while True:
            esito, chi = await partite_repo.apri_gruppo(guild.id, giocatori, gioco, puntata, impostazioni.attesa_gioco)
            if esito is EsitoApertura.APERTA:
                if esclusi:
                    await interaction.followup.send(await testo_per(interaction, "sala_esclusi", pubblica=True, chi=" ".join(f"<@{u}>" for u in esclusi)), allowed_mentions=NESSUNA_MENZIONE)
                return giocatori
            giocatori = [u for u in giocatori if u != chi]
            esclusi.append(chi)
            if len(giocatori) < minimo:
                await interaction.followup.send(await testo_per(interaction, "sala_non_parte_soldi", pubblica=True, chi=" ".join(f"<@{u}>" for u in esclusi)), allowed_mentions=NESSUNA_MENZIONE)
                return None

    async def _gratis(self, interaction: discord.Interaction, nome: str, minimo: int, massimo: int, motore) -> None:
        """Impiccato e quiz: niente puntata, un piccolo premio con il tetto del giorno."""
        if not await self._attivo(interaction):
            return
        guild, canale = interaction.guild, interaction.channel
        chiave = (guild.id, getattr(canale, "id", 0))
        if chiave in self._occupati:
            await interaction.response.send_message(await testo_per(interaction, "sala_canale_occupato"), ephemeral=True)
            return
        impostazioni = (await leveling_settings_repo.get_config(guild.id)).impostazioni
        self._occupati.add(chiave)
        try:
            await interaction.response.defer()
            giocatori = await apri_lobby(
                interaction, minimo, massimo, "sala_intro_gratis", SECONDI_LOBBY, verifica=self._verifica_ingresso(interaction.user.id),
                gioco=await testo_per(interaction, f"sala_nome_{nome}", pubblica=True), moneta=impostazioni.currency_name, tetto=TETTO_PREMI_GIORNO,
            )
            if giocatori is None:
                await interaction.followup.send(await testo_per(interaction, "sala_non_parte", pubblica=True))
                return
            try:
                await motore(Tavolo(interaction, giocatori, 0, impostazioni.currency_name))
            except Exception:
                logger.exception("Partita %s in errore", nome)
        finally:
            self._occupati.discard(chiave)

    # ------------------------------------------------------------------ comandi
    @comando_di_gruppo("sala", nome="roulette", descrizione="Roulette a più giocatori: una puntata uguale per tutti, un solo giro.")
    @app_commands.describe(puntata="Monete da puntare, uguali per tutti")
    async def roulette(self, interaction: discord.Interaction, puntata: app_commands.Range[int, 1, PUNTATA_TETTO]) -> None:
        await self._partita(interaction, "roulette", puntata)

    @comando_di_gruppo("sala", nome="corsa", descrizione="Corsa di animali: chi arriva primo prende il piatto.")
    @app_commands.describe(puntata="Monete da puntare, uguali per tutti")
    async def corsa(self, interaction: discord.Interaction, puntata: app_commands.Range[int, 1, PUNTATA_TETTO]) -> None:
        await self._partita(interaction, "corsa", puntata)

    @comando_di_gruppo("sala", nome="lotta", descrizione="Lotta fino a 6 con il tuo animale: l'ultimo in piedi prende il piatto.")
    @app_commands.describe(puntata="Monete da puntare, uguali per tutti")
    async def lotta(self, interaction: discord.Interaction, puntata: app_commands.Range[int, 1, PUNTATA_TETTO]) -> None:
        await self._partita(interaction, "lotta", puntata)

    @comando_di_gruppo("sala", nome="combattimento", descrizione="Combattimento fino a 6 con regole tue: vite, giri e oggetti.")
    @app_commands.describe(
        puntata="Monete da puntare, uguali per tutti", vite=f"Vite di ciascuno ({cb.VITE_MIN}-{cb.VITE_MAX}, di base {cb.VITE_BASE})",
        giri=f"Giri massimi ({cb.GIRI_MIN}-{cb.GIRI_MAX}, di base {cb.GIRI_BASE})", oggetti="Pozione e scudo ammessi (di base no)",
    )
    async def combattimento(
        self, interaction: discord.Interaction, puntata: app_commands.Range[int, 1, PUNTATA_TETTO],
        vite: app_commands.Range[int, cb.VITE_MIN, cb.VITE_MAX] = cb.VITE_BASE,
        giri: app_commands.Range[int, cb.GIRI_MIN, cb.GIRI_MAX] = cb.GIRI_BASE, oggetti: bool = False,
    ) -> None:
        errore = cb.controlla_regole(vite, giri)
        if errore is not None:  # i limiti stanno in un punto solo (core/combattimento_logic.py)
            await interaction.response.send_message(f"❌ {errore}", ephemeral=True)
            return
        await self._partita(interaction, "combattimento", puntata, SimpleNamespace(vite=vite, giri=giri, oggetti=oggetti))

    @comando_di_gruppo("sala", nome="bomba", descrizione="Taglia il filo giusto: chi fa esplodere la bomba esce, l'ultimo vince.")
    @app_commands.describe(puntata="Monete da puntare, uguali per tutti")
    async def bomba(self, interaction: discord.Interaction, puntata: app_commands.Range[int, 1, PUNTATA_TETTO]) -> None:
        await self._partita(interaction, "bomba", puntata)

    @comando_di_gruppo("sala", nome="tamburo", descrizione="Un tamburo con una sfera rossa: chi la trova esce, l'ultimo prende il piatto.")
    @app_commands.describe(puntata="Monete da puntare, uguali per tutti")
    async def tamburo(self, interaction: discord.Interaction, puntata: app_commands.Range[int, 1, PUNTATA_TETTO]) -> None:
        await self._partita(interaction, "tamburo", puntata)

    @comando_di_gruppo("sala", nome="carte", descrizione="Carte a turni: stesso colore o stesso numero, chi finisce le carte vince.")
    @app_commands.describe(puntata="Monete da puntare, uguali per tutti")
    async def carte(self, interaction: discord.Interaction, puntata: app_commands.Range[int, 1, PUNTATA_TETTO]) -> None:
        await self._partita(interaction, "carte", puntata)

    @comando_di_gruppo("sala", nome="bingo", descrizione="Bingo tra membri: completa una riga della cartella per vincere il piatto.")
    @app_commands.describe(puntata="Monete da puntare, uguali per tutti")
    async def bingo(self, interaction: discord.Interaction, puntata: app_commands.Range[int, 1, PUNTATA_TETTO]) -> None:
        await self._partita(interaction, "bingo", puntata)

    @comando_di_gruppo("sala", nome="impiccato", descrizione="Impiccato di gruppo: indovinate la parola insieme e vincete un premio.")
    async def impiccato(self, interaction: discord.Interaction) -> None:
        await self._gratis(interaction, "impiccato", 1, 10, gioca_impiccato)

    @comando_di_gruppo("sala", nome="quiz", descrizione="Quiz a tempo con premio in monete: cinque domande, quattro risposte.")
    async def quiz(self, interaction: discord.Interaction) -> None:
        await self._gratis(interaction, "quiz", 1, 10, gioca_quiz)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SalaCog(bot))
