"""
cogs/leveling/negozio_extra.py
==============================
Negozio avanzato: oggetti a rotazione e offerte lampo con bottone (/admin-economia-negozio rotazione, offerta), ricette per
creare oggetti da altri oggetti (comandi «ricetta» di /admin-economia-negozio, /monete shop ricette, crea). Il prezzo effettivo si
calcola in un solo punto (core/negozio_logic.py) e si applica dentro la scrittura dell'acquisto.
Funzioni coperte: ECO-075, ECO-076, ECO-078
Dipende da: core/repositories/negozio_repo.py, core/repositories/shop_repo.py
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from cogs.leveling.leveling import _comando_rifiutato
from core.command_groups import CogConGruppi, SOTTOGRUPPI, comando_di_gruppo, togli_comandi_del_cog
from core.i18n import testo_per
from core.negozio_logic import DURATA_MASSIMA_OFFERTA_MIN, MAX_INGREDIENTI, MAX_ROTAZIONE, prezzo_con_sconto
from core.repositories.leveling_settings_repo import leveling_settings_repo
from core.repositories.negozio_repo import EsitoRicetta, negozio_repo
from core.repositories.shop_repo import shop_repo
from core.ui_base import BaseView
from core.giro_periodico import giro_periodico

logger = logging.getLogger("iyokai.negozio_extra")
NESSUNA_MENZIONE = discord.AllowedMentions.none()
SG_SHOP = SOTTOGRUPPI["monete shop"]
SG_ROT = ("rotazione", "Oggetti che ruotano ogni giorno")
SG_OFF = ("offerta", "Offerte lampo a tempo")
SG_RIC = ("ricetta", "Ricette per creare oggetti")


def leggi_ingredienti(testo: str) -> dict[int, int] | None:
    """«3:2, 5:1» (ID oggetto: quantità) -> {3: 2, 5: 1}. None se il testo non è valido."""
    risultato: dict[int, int] = {}
    for pezzo in testo.split(","):
        parti = pezzo.strip().split(":")
        if len(parti) != 2 or not all(p.strip().isdigit() for p in parti):
            return None
        item, q = int(parti[0]), int(parti[1])
        if not (1 <= item <= 2_147_483_647 and 1 <= q <= 100) or item in risultato:
            return None
        risultato[item] = q
    return risultato if 1 <= len(risultato) <= MAX_INGREDIENTI else None


class OffertaView(BaseView):
    """Bottone «Compra» dell'offerta lampo: l'acquisto passa dal codice di /monete shop buy (scrittura atomica)."""

    def __init__(self, item_id: int, prezzo: int, etichetta: str, secondi: int) -> None:
        super().__init__(timeout=secondi)
        self.item_id, self.prezzo = item_id, prezzo
        self.compra.label = etichetta[:45]

    @discord.ui.button(style=discord.ButtonStyle.success)
    async def compra(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        cog = interaction.client.get_cog("LevelingCog")
        if cog is None or interaction.guild is None:
            await interaction.response.send_message(await testo_per(interaction, "neg_non_disponibile"), ephemeral=True)
            return
        # prezzo_atteso = quello dell'offerta: se è finita o cambiata, non si compra e lo si dice
        await cog._acquista(interaction, self.item_id, prezzo_atteso=self.prezzo)


class NegozioExtraCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._pulizia.start()

    def cog_unload(self) -> None:
        self._pulizia.cancel()
        togli_comandi_del_cog(self)

    @giro_periodico(hours=6)
    async def _pulizia(self) -> None:
        await negozio_repo.pulisci_offerte()

    @_pulizia.before_loop
    async def _prima(self) -> None:
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------------ admin: rotazione (ECO-075)
    @comando_di_gruppo("admin-economia-negozio", nome="quanti", descrizione="Quanti oggetti a rotazione sono in vetrina ogni giorno (0 = spenta).", sottogruppo=SOTTOGRUPPI["admin-economia-negozio rotazione"])
    @app_commands.describe(quanti=f"Oggetti in vetrina al giorno (0-{MAX_ROTAZIONE})")
    async def rotazione_quanti(self, interaction: discord.Interaction, quanti: app_commands.Range[int, 0, MAX_ROTAZIONE]) -> None:
        if await _comando_rifiutato(interaction):
            return
        await negozio_repo.imposta_rotazione(interaction.guild.id, quanti)
        await interaction.response.send_message(await testo_per(interaction, "neg_rotazione_ok", n=quanti), ephemeral=True)

    @comando_di_gruppo("admin-economia-negozio", nome="oggetto", descrizione="Mette un oggetto tra quelli che ruotano (o lo toglie).", sottogruppo=SOTTOGRUPPI["admin-economia-negozio rotazione"])
    @app_commands.describe(oggetto="ID dell'oggetto", ruota="Sì = ruota, no = sempre in vetrina")
    async def rotazione_oggetto(self, interaction: discord.Interaction, oggetto: app_commands.Range[int, 1, 2_147_483_647], ruota: bool) -> None:
        if await _comando_rifiutato(interaction):
            return
        ok = await negozio_repo.imposta_a_rotazione(interaction.guild.id, oggetto, ruota)
        await interaction.response.send_message(await testo_per(interaction, "neg_oggetto_ok" if ok else "neg_oggetto_no"), ephemeral=True)

    # ------------------------------------------------------------------ admin: offerte lampo (ECO-076)
    @comando_di_gruppo("admin-economia-negozio", nome="lampo", descrizione="Lancia un'offerta lampo a tempo con il bottone per comprare.", sottogruppo=SOTTOGRUPPI["admin-economia-negozio offerta"])
    @app_commands.describe(
        oggetto="ID dell'oggetto", sconto="Sconto in percentuale (1-90)", minuti="Durata in minuti",
        usi="Quante volte si può comprare (vuoto = senza limite)", canale="Dove annunciarla (vuoto = qui)",
    )
    async def offerta_lampo(
        self, interaction: discord.Interaction, oggetto: app_commands.Range[int, 1, 2_147_483_647],
        sconto: app_commands.Range[int, 1, 90], minuti: app_commands.Range[int, 1, DURATA_MASSIMA_OFFERTA_MIN],
        usi: app_commands.Range[int, 1, 100_000] | None = None, canale: discord.TextChannel | None = None,
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        g = interaction.guild
        item = await shop_repo.get_item(oggetto, g.id)
        if item is None:
            await interaction.response.send_message(await testo_per(interaction, "neg_oggetto_no"), ephemeral=True)
            return
        dove = canale or interaction.channel
        if not isinstance(dove, discord.abc.Messageable) or not dove.permissions_for(g.me).send_messages:
            await interaction.response.send_message(await testo_per(interaction, "neg_canale_no"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await negozio_repo.crea_offerta(g.id, oggetto, sconto, minuti, usi, interaction.user.id)
        moneta = (await leveling_settings_repo.get_config(g.id)).impostazioni.currency_name
        prezzo = prezzo_con_sconto(item.price, sconto)
        etichetta = await testo_per(interaction, "neg_bottone", pubblica=True, prezzo=prezzo, moneta=moneta)
        testo = await testo_per(interaction, "neg_annuncio", pubblica=True, nome=item.name[:80], sconto=sconto, prezzo=prezzo, vecchio=item.price, moneta=moneta, minuti=minuti)
        try:
            await dove.send(testo[:2000], view=OffertaView(oggetto, prezzo, etichetta, minuti * 60), allowed_mentions=NESSUNA_MENZIONE)
        except discord.HTTPException:
            await interaction.followup.send(await testo_per(interaction, "neg_canale_no"), ephemeral=True)
            return
        await interaction.followup.send(await testo_per(interaction, "neg_lampo_ok"), ephemeral=True)

    @comando_di_gruppo("admin-economia-negozio", nome="chiudi", descrizione="Chiude subito l'offerta lampo di un oggetto.", sottogruppo=SOTTOGRUPPI["admin-economia-negozio offerta"])
    @app_commands.describe(oggetto="ID dell'oggetto")
    async def offerta_chiudi(self, interaction: discord.Interaction, oggetto: app_commands.Range[int, 1, 2_147_483_647]) -> None:
        if await _comando_rifiutato(interaction):
            return
        ok = await negozio_repo.togli_offerta(interaction.guild.id, oggetto)
        await interaction.response.send_message(await testo_per(interaction, "neg_chiusa" if ok else "neg_nessuna_offerta"), ephemeral=True)

    # ------------------------------------------------------------------ admin: ricette (ECO-078)
    @comando_di_gruppo("admin-economia-negozio", nome="crea", descrizione="Crea una ricetta: certi oggetti diventano un altro oggetto.", sottogruppo=SOTTOGRUPPI["admin-economia-negozio ricetta"])
    @app_commands.describe(
        nome="Nome della ricetta", risultato="ID dell'oggetto che si ottiene", ingredienti="Ingredienti come ID:quantità, separati da virgola (massimo 5)",
        quantita="Quanti pezzi si ottengono (1-100)", costo="Monete da pagare per crearlo (0 = niente)",
    )
    async def ricetta_crea(
        self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, 40], risultato: app_commands.Range[int, 1, 2_147_483_647],
        ingredienti: app_commands.Range[str, 3, 120], quantita: app_commands.Range[int, 1, 100] = 1, costo: app_commands.Range[int, 0, 1_000_000] = 0,
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        letti = leggi_ingredienti(ingredienti)
        if letti is None:
            await interaction.response.send_message(await testo_per(interaction, "neg_ingredienti_no", massimo=MAX_INGREDIENTI), ephemeral=True)
            return
        esito = await negozio_repo.crea_ricetta(interaction.guild.id, nome.strip(), risultato, quantita, costo, letti)
        await interaction.response.send_message(await testo_per(interaction, f"neg_ricetta_{esito}"), ephemeral=True)

    @comando_di_gruppo("admin-economia-negozio", nome="elimina", descrizione="Elimina una ricetta.", sottogruppo=SOTTOGRUPPI["admin-economia-negozio ricetta"])
    @app_commands.describe(nome="Nome della ricetta")
    async def ricetta_elimina(self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, 40]) -> None:
        if await _comando_rifiutato(interaction):
            return
        ok = await negozio_repo.elimina_ricetta(interaction.guild.id, nome)
        await interaction.response.send_message(await testo_per(interaction, "neg_ricetta_eliminata" if ok else "neg_ricetta_non_esiste"), ephemeral=True)

    # ------------------------------------------------------------------ per tutti
    @comando_di_gruppo("monete", nome="ricette", descrizione="Le ricette del server: cosa si crea con cosa.", sottogruppo=SG_SHOP)
    async def ricette(self, interaction: discord.Interaction) -> None:
        if await _comando_rifiutato(interaction):
            return
        g = interaction.guild.id
        elenco = await negozio_repo.ricette(g)
        if not elenco:
            await interaction.response.send_message(await testo_per(interaction, "neg_nessuna_ricetta"), ephemeral=True)
            return
        nomi = {o.id: o.name for o in await shop_repo.list_items(g)}
        righe = [
            f"**{r.nome[:40]}**: " + " + ".join(f"{q}× {nomi.get(i, '?')[:40]}" for i, q in r.ingredienti)
            + f" → {r.risultato_q}× {nomi.get(r.risultato_item, '?')[:40]}" + (f" ({r.costo})" if r.costo else "")
            for r in elenco
        ]
        await interaction.response.send_message("\n".join(righe)[:1900], ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)

    @comando_di_gruppo("monete", nome="crea", descrizione="Crea un oggetto da altri oggetti con una ricetta.", sottogruppo=SG_SHOP)
    @app_commands.describe(ricetta="Nome della ricetta (vedi /monete shop ricette)")
    async def crea(self, interaction: discord.Interaction, ricetta: app_commands.Range[str, 1, 40]) -> None:
        if await _comando_rifiutato(interaction):
            return
        esito = await negozio_repo.crea_oggetto(interaction.guild.id, interaction.user.id, ricetta)
        await interaction.response.send_message(await testo_per(interaction, f"neg_crea_{esito.value}"), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(NegozioExtraCog(bot))
