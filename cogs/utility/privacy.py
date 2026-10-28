"""
cogs/utility/privacy.py
=======================
I tuoi dati personali: esportazione (art. 15) e richiesta di cancellazione
(art. 17), più il lavoro del proprietario sulle richieste.
Comandi: `/utility privacy esporta|cancella`, `/owner privacy richieste|approva|rifiuta`.
Funzioni coperte: SPEC §19 (NF-04, #37, #75)
Dipende da: core/forget_user_service.py, core/data_registry.py, core/invio_file.py

Ban e kick di sicurezza non si cancellano (#37, #46): la risposta lo dice chiaro.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from cogs.utility._owner_pagine import invia_a_pagine
from core import forget_user_service as servizio
from core.i18n import testo_per
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.invio_file import invia_file
from core.repositories.data_deletion_request_repo import (
    MOTIVO_MAX,
    STATO_RIFIUTATA,
    data_deletion_request_repo,
)

logger = logging.getLogger("iyokai.privacy")

SOTTOGRUPPO_UTENTE = ("privacy", "I tuoi dati personali: copia e cancellazione")
SOTTOGRUPPO_OWNER = ("privacy", "Richieste di cancellazione dei dati")

TESTO_CANCELLA = (
    "Richiesta ricevuta (numero {numero}). Il proprietario del bot la esamina e ti scrive in privato.\n"
    "Cosa succede: cancello o rendo anonimi i tuoi dati (livelli, monete, clan, preferenze, ticket, "
    "suggerimenti, token di ripristino).\n"
    "Cosa resta: ban, kick, registri di sicurezza e ban globali, per proteggere i server, e gli sban programmati. "
    "La richiesta stessa, con il motivo che scrivi, resta 24 mesi come prova di ciò che è stato fatto. Se sei titolare di un clan, passa al co-titolare o al membro più anziano; "
    "se sei solo, il clan viene sciolto."
)


class PrivacyCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------ utente
    @comando_di_gruppo(
        "utility",
        nome="esporta",
        descrizione="Ricevi una copia dei dati che il bot conserva su di te.",
        sottogruppo=SOTTOGRUPPO_UTENTE,
    )
    @app_commands.checks.cooldown(1, 60.0, key=lambda i: i.user.id)
    async def privacy_esporta(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        dati = await servizio.esporta_utente(db.pool, interaction.user.id)
        testo, accorciate = servizio.serializza_esportazione(dati)
        messaggio = "Ecco la copia dei tuoi dati. Solo tu la vedi."
        if not dati["tabelle"]:
            messaggio = "Non conservo dati su di te. Il file contiene solo l'intestazione."
        if accorciate:
            messaggio += " Alcune tabelle erano troppo grandi e sono state accorciate: " + ", ".join(accorciate) + "."
        if dati.get("troncate"):
            messaggio += (
                f" Ho esportato al massimo {servizio.RIGHE_MAX_PER_TABELLA} righe per tabella; ce ne sono di più in: "
                + ", ".join(dati["troncate"])
                + ". Scrivi al proprietario per il resto."
            )
        await invia_file(
            interaction.followup.send,
            testo,
            f"iyokai-dati-{interaction.user.id}.json",
            contenuto=messaggio,
            ephemeral=True,
        )

    @comando_di_gruppo(
        "utility",
        nome="cancella",
        descrizione="Chiedi la cancellazione dei tuoi dati personali.",
        sottogruppo=SOTTOGRUPPO_UTENTE,
    )
    @app_commands.describe(motivo="Perché lo chiedi (facoltativo)")
    async def privacy_cancella(
        self,
        interaction: discord.Interaction,
        motivo: app_commands.Range[str, 1, MOTIVO_MAX] | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        numero, nuova = await data_deletion_request_repo.crea(interaction.user.id, motivo)
        if not nuova:
            await interaction.followup.send(
                await testo_per(interaction, "priv_gia_in_attesa", numero=numero),
                ephemeral=True,
            )
            return
        await interaction.followup.send(TESTO_CANCELLA.format(numero=numero), ephemeral=True)

    # ------------------------------------------------------------ proprietario
    @comando_di_gruppo(
        "owner",
        nome="richieste",
        descrizione="Elenca le richieste di cancellazione dei dati in attesa.",
        sottogruppo=SOTTOGRUPPO_OWNER,
    )
    async def privacy_richieste(self, interaction: discord.Interaction) -> None:
        richieste = await data_deletion_request_repo.in_attesa()
        if not richieste:
            await interaction.response.send_message("Nessuna richiesta in attesa.", ephemeral=True)
            return
        righe = [
            f"**{r['id']}** · utente `{r['user_id']}` · {discord.utils.format_dt(r['richiesta_il'], 'R')}"
            + (f" · {r['motivo']}" if r["motivo"] else "")
            for r in richieste
        ]
        await invia_a_pagine(interaction, "Richieste di cancellazione", righe)

    @comando_di_gruppo(
        "owner",
        nome="approva",
        descrizione="Esegue una richiesta di cancellazione e avvisa l'utente.",
        sottogruppo=SOTTOGRUPPO_OWNER,
    )
    @app_commands.describe(richiesta="Il numero della richiesta")
    async def privacy_approva(
        self, interaction: discord.Interaction, richiesta: app_commands.Range[int, 1, 2**53 - 1]
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        esito = await servizio.esegui_richiesta(db.pool, richiesta, interaction.user.id)
        if esito is None:
            await interaction.followup.send(
                f"Richiesta {richiesta} non trovata o già chiusa.", ephemeral=True
            )
            return
        testo = servizio.testo_rapporto(esito["rapporto"])
        avvisato = await self._avvisa(esito["user_id"], "I tuoi dati sono stati cancellati.\n" + testo)
        chiusura = "" if avvisato else "\nL'utente ha i messaggi privati chiusi: non è stato avvisato."
        await interaction.followup.send(
            f"Richiesta {richiesta} eseguita per `{esito['user_id']}`.\n{testo}{chiusura}", ephemeral=True
        )

    @comando_di_gruppo(
        "owner",
        nome="rifiuta",
        descrizione="Rifiuta una richiesta di cancellazione e dì all'utente perché.",
        sottogruppo=SOTTOGRUPPO_OWNER,
    )
    @app_commands.describe(richiesta="Il numero della richiesta", motivo="Il motivo, che l'utente leggerà")
    async def privacy_rifiuta(
        self,
        interaction: discord.Interaction,
        richiesta: app_commands.Range[int, 1, 2**53 - 1],
        motivo: app_commands.Range[str, 1, MOTIVO_MAX],
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        riga = await data_deletion_request_repo.get(richiesta)
        chiusa = riga is not None and await data_deletion_request_repo.chiudi(
            richiesta, STATO_RIFIUTATA, interaction.user.id, {"motivo": motivo}
        )
        if not chiusa:
            await interaction.followup.send(
                f"Richiesta {richiesta} non trovata o già chiusa.", ephemeral=True
            )
            return
        avvisato = await self._avvisa(riga["user_id"], f"La tua richiesta di cancellazione è stata rifiutata: {motivo}")
        await interaction.followup.send(
            f"Richiesta {richiesta} rifiutata."
            + ("" if avvisato else " L'utente ha i messaggi privati chiusi: non è stato avvisato."),
            ephemeral=True,
        )

    async def _avvisa(self, user_id: int, testo: str) -> bool:
        """Messaggio privato all'utente. False se non si può (DM chiusi): mai un'eccezione."""
        try:
            utente = await self.bot.fetch_user(user_id)
            await utente.send(testo)
            return True
        except discord.HTTPException:
            logger.info("Utente %s non raggiungibile in privato.", user_id)
            return False


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PrivacyCog(bot))
