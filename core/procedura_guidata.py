"""
core/procedura_guidata.py
=========================
Schema riusabile per le procedure guidate a passi: una finestra legata a chi l'ha avviata, con Avanti,
Indietro, Annulla e un riepilogo finale da confermare. Tutto resta in memoria fino alla conferma:
annullare o lasciar scadere non scrive niente. I permessi si rileggono a ogni passo e alla conferma.
Funzioni coperte: SPEC §10 (UTL-121; D124)
Dipende da: core/ui_base.py, core/i18n.py
"""

from __future__ import annotations

import enum
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import discord

from core.i18n import t
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.procedura_guidata")

TEMPO_MASSIMO_SECONDI = 600
NESSUNA_MENZIONE = discord.AllowedMentions.none()


class Fase(enum.Enum):
    IN_CORSO = "in_corso"
    CONFERMATA = "confermata"
    ANNULLATA = "annullata"
    SCADUTA = "scaduta"


@dataclass(frozen=True)
class Passo:
    """Un passo: `chiave` è anche la chiave del testo; `richiesti` sono i dati senza i quali non si va avanti."""

    chiave: str
    richiesti: tuple[str, ...] = ()


@dataclass
class StatoProcedura:
    """La parte pura: a che passo si è e cosa è stato scelto. Dopo l'ultimo passo c'è il riepilogo."""

    autore_id: int
    passi: tuple[Passo, ...]
    dati: dict[str, Any] = field(default_factory=dict)
    indice: int = 0
    fase: Fase = Fase.IN_CORSO

    @property
    def al_riepilogo(self) -> bool:
        return self.indice >= len(self.passi)

    @property
    def passo(self) -> Passo | None:
        return None if self.al_riepilogo else self.passi[self.indice]

    def mancanti(self) -> tuple[str, ...]:
        """I dati richiesti dal passo in corso (o da tutti, al riepilogo) che non sono ancora stati scelti."""
        passi = self.passi if self.al_riepilogo else (self.passi[self.indice],)
        return tuple(k for p in passi for k in p.richiesti if self.dati.get(k) in (None, "", ()))

    def avanti(self) -> tuple[str, ...]:
        """Passa al passo dopo. Se mancano dati resta fermo e li elenca."""
        if self.fase is not Fase.IN_CORSO or self.al_riepilogo:
            return ()
        mancano = self.mancanti()
        if not mancano:
            self.indice += 1
        return mancano

    def indietro(self) -> None:
        if self.fase is Fase.IN_CORSO and self.indice > 0:
            self.indice -= 1

    def annulla(self, fase: Fase = Fase.ANNULLATA) -> None:
        """Niente resta scritto: i dati si buttano."""
        if self.fase is Fase.IN_CORSO:
            self.fase = fase
            self.dati.clear()

    def conferma(self) -> bool:
        """Vero una volta sola, e solo dal riepilogo con tutti i dati: chi conferma due volte non scrive due volte."""
        if self.fase is not Fase.IN_CORSO or not self.al_riepilogo or self.mancanti():
            return False
        self.fase = Fase.CONFERMATA
        return True


# Chi decide se la persona può ancora andare avanti: None se sì, altrimenti il testo del rifiuto.
Permesso = Callable[[discord.Interaction], Awaitable[str | None]]
# Gli elementi (menu, bottoni) di un passo.
Costruttore = Callable[["VistaGuidata"], list[discord.ui.Item]]
# Il testo (descrizione) di un passo o del riepilogo.
Testo = Callable[["VistaGuidata"], str]
# La scrittura finale: riceve i dati e dà il testo da mostrare. Lancia ValueError(testo) per un rifiuto.
Conferma = Callable[[discord.Interaction, dict[str, Any]], Awaitable[str]]


class VistaGuidata(BaseView):
    """La finestra a passi: solo chi l'ha avviata, solo se ha ancora il permesso, scade da sola."""

    def __init__(
        self,
        stato: StatoProcedura,
        *,
        titolo: str,
        lingua: str,
        permesso: Permesso,
        costruttori: dict[str, Costruttore],
        testi: dict[str, Testo],
        riepilogo: Testo,
        conferma: Conferma,
        timeout: float = TEMPO_MASSIMO_SECONDI,
    ) -> None:
        super().__init__(timeout=timeout)
        self.stato = stato
        self.titolo = titolo
        self.lingua = lingua
        self._permesso = permesso
        self._costruttori = costruttori
        self._testi = testi
        self._riepilogo = riepilogo
        self._conferma = conferma
        self.message: discord.Message | discord.InteractionMessage | None = None
        self.ricostruisci()

    # ---- controllo ----
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        return await self.autorizza(interaction)

    async def autorizza(self, interaction: discord.Interaction) -> bool:
        """Chi clicca (o invia una finestra) è l'autore e ha ancora il permesso: riletto adesso, ogni volta."""
        if interaction.user.id != self.stato.autore_id:
            await self._rifiuta(interaction, t("guidata_non_tua", self.lingua))
            return False
        rifiuto = await self._permesso(interaction)
        if rifiuto is not None:
            self.stato.annulla()
            self.stop()
            await self._rifiuta(interaction, rifiuto, chiudi=True)
            return False
        return True

    async def _rifiuta(self, interaction: discord.Interaction, testo: str, *, chiudi: bool = False) -> None:
        try:
            if interaction.response.is_done():
                await interaction.followup.send(testo[:2000], ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)
            else:
                await interaction.response.send_message(testo[:2000], ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)
            if chiudi and self.message is not None:
                await self.message.edit(content=t("guidata_annullata", self.lingua), embed=None, view=None)
        except discord.HTTPException:
            pass

    # ---- disegno ----
    def embed(self) -> discord.Embed:
        s = self.stato
        if s.al_riepilogo:
            nome = t("guidata_riepilogo_titolo", self.lingua)
            corpo = self._riepilogo(self)
        else:
            nome = t(f"{s.passo.chiave}_titolo", self.lingua)
            corpo = self._testi[s.passo.chiave](self)
        totale = len(s.passi) + 1
        intestazione = t("guidata_passo", self.lingua, n=s.indice + 1, totale=totale, nome=nome)
        embed = discord.Embed(title=f"{self.titolo} · {intestazione}"[:256], description=corpo[:4000])
        embed.set_footer(text=t("guidata_footer", self.lingua, minuti=int(self.timeout or TEMPO_MASSIMO_SECONDI) // 60))
        return embed

    def ricostruisci(self) -> None:
        self.clear_items()
        s = self.stato
        if not s.al_riepilogo:
            for elemento in self._costruttori.get(s.passo.chiave, lambda v: [])(self):
                self.add_item(elemento)
        indietro = discord.ui.Button(label=t("guidata_indietro", self.lingua), row=4, disabled=s.indice == 0)
        indietro.callback = self._indietro
        ultimo = s.al_riepilogo
        avanti = discord.ui.Button(
            label=t("guidata_conferma" if ultimo else "guidata_avanti", self.lingua),
            style=discord.ButtonStyle.success, row=4,
        )
        avanti.callback = self._conferma_premuto if ultimo else self._avanti
        annulla = discord.ui.Button(label=t("guidata_annulla", self.lingua), style=discord.ButtonStyle.danger, row=4)
        annulla.callback = self._annulla
        for bottone in (indietro, avanti, annulla):
            self.add_item(bottone)

    async def aggiorna(self, interaction: discord.Interaction) -> None:
        """Ridisegna il messaggio dopo una scelta (usabile dai menu e dalle finestre dei passi)."""
        self.ricostruisci()
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=self.embed(), view=self)
        else:
            await interaction.response.edit_message(embed=self.embed(), view=self)

    # ---- bottoni ----
    async def _indietro(self, interaction: discord.Interaction) -> None:
        self.stato.indietro()
        await self.aggiorna(interaction)

    async def _avanti(self, interaction: discord.Interaction) -> None:
        if self.stato.avanti():
            await interaction.response.send_message(t("guidata_mancano_dati", self.lingua), ephemeral=True)
            return
        await self.aggiorna(interaction)

    async def _annulla(self, interaction: discord.Interaction) -> None:
        self.stato.annulla()
        self.stop()
        await interaction.response.edit_message(content=t("guidata_annullata", self.lingua), embed=None, view=None)

    async def _conferma_premuto(self, interaction: discord.Interaction) -> None:
        if not self.stato.conferma():  # prima di ogni await: un secondo clic trova la fase già chiusa
            await interaction.response.send_message(t("guidata_mancano_dati", self.lingua), ephemeral=True)
            return
        self.stop()
        await interaction.response.defer()
        try:
            testo = await self._conferma(interaction, dict(self.stato.dati))
        except ValueError as rifiuto:
            testo = str(rifiuto)
        except Exception:  # noqa: BLE001 - la finestra non deve restare muta
            logger.exception("Procedura guidata: scrittura finale fallita.")
            testo = t("guidata_errore", self.lingua)
        await interaction.edit_original_response(content=testo[:2000], embed=None, view=None, allowed_mentions=NESSUNA_MENZIONE)

    async def on_timeout(self) -> None:
        self.stato.annulla(Fase.SCADUTA)
        if self.message is not None:
            try:
                await self.message.edit(content=t("guidata_scaduta", self.lingua), embed=None, view=None)
            except discord.HTTPException:
                pass
