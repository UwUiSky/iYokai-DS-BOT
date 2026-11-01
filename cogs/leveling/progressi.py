"""
cogs/leveling/progressi.py
==========================
/level progressi: una finestra con un menu (missioni del giorno, della settimana e del server, traguardi,
serie di giorni con protezione, pass di 90 giorni con traccia premium, profilo globale). /economia
progressi: lo staff li accende e sceglie l'obiettivo del server. Le monete le accredita
core/progressi_service.py in modo atomico.
Funzioni coperte: SPEC §23.17 (NF-41, D49, D51)
Dipende da: core/progressi_service.py, core/progressi_logic.py
"""

from __future__ import annotations


import discord
from discord import app_commands
from discord.ext import commands

from cogs.leveling.leveling import _comando_rifiutato
from core import progressi_service as servizio
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.profile_logic import PER_ID
from core.progressi_logic import (
    MISSIONI_GIORNO,
    MISSIONI_SERVER,
    MISSIONI_SETTIMANA,
    OBIETTIVO_SERVER_MAX,
    OBIETTIVO_SERVER_MIN,
    PASS_PREZZO_PREMIUM,
    PREMI_SERIE,
    SCUDI_MAX,
    SCUDO_PREZZO,
    SERIE_LIMITE_ORE,
    TRAGUARDO_PER_CHIAVE,
    ProfiloGlobale,
    lunedi_di,
    minimo_partecipazione,
    prossima_tappa,
    scade_tra_ore,
    serie_attuale,
    stagione_di,
    stato_missione,
    stato_missione_server,
    testo_pass,
    testo_profilo_globale,
    testo_traguardi,
)
from core.ui_base import BaseView

MENU = (
    ("missioni", "Missioni"),
    ("traguardi", "Traguardi"),
    ("serie", "Serie di giorni"),
    ("pass", "Pass di 90 giorni"),
    ("globale", "Il mio profilo globale"),
)
TITOLI = dict(MENU)
SPENTO = (
    "Missioni, serie, traguardi e pass sono spenti su questo server. "
    "Un amministratore li accende con `/economia progressi`."
)


def _testo_nuovi(nuovi: tuple[str, ...]) -> str:
    if not nuovi:
        return ""
    return "\nNuovi traguardi: " + ", ".join(
        f"{TRAGUARDO_PER_CHIAVE[c].emoji} {TRAGUARDO_PER_CHIAVE[c].testo}" for c in nuovi if c in TRAGUARDO_PER_CHIAVE
    )


def _testo_oggetti(oggetti: tuple[str, ...]) -> str:
    if not oggetti:
        return ""
    return "\nNuovi oggetti per il profilo: " + ", ".join(
        f"{PER_ID[i].emoji or '🎨'} {PER_ID[i].nome}" for i in oggetti if i in PER_ID
    ) + " (si mettono con `/level collezione equipaggia`)."


# ---------------------------------------------------------------- le schede
async def _scheda_missioni(guild_id: int, user_id: int) -> tuple[str, bool]:
    """(testo, c'è qualcosa da riscuotere)."""
    repo = servizio.progressi_repo
    await servizio.svuota(guild_id, user_id)
    oggi = servizio._oggi()
    lunedi = lunedi_di(oggi)
    giorno = await repo.missioni_di(guild_id, user_id, oggi)
    settimana = await repo.missioni_di(guild_id, user_id, lunedi)
    base = await servizio.obiettivo_server_base(guild_id)
    fatte = await repo.server_riscattate(guild_id, user_id, lunedi)
    pronto = any(
        giorno.get(m.chiave, (0, False))[0] >= m.obiettivo and not giorno.get(m.chiave, (0, False))[1]
        for m in MISSIONI_GIORNO
    ) or any(
        settimana.get(m.chiave, (0, False))[0] >= m.obiettivo and not settimana.get(m.chiave, (0, False))[1]
        for m in MISSIONI_SETTIMANA
    )
    righe_server = []
    for ms in MISSIONI_SERVER:
        totale, _ = await repo.totale_server(guild_id, lunedi, ms.personale, minimo_partecipazione(ms))
        mio = settimana.get(ms.personale, (0, False))[0]
        righe_server.append(stato_missione_server(ms, base, totale, mio, ms.chiave in fatte))
        if "🎁" in righe_server[-1]:
            pronto = True
    testo = (
        "**Di oggi** (si azzerano a mezzanotte UTC)\n"
        + "\n".join(stato_missione(m, *giorno.get(m.chiave, (0, False))) for m in MISSIONI_GIORNO)
        + "\n\n**Della settimana** (dal lunedì)\n"
        + "\n".join(stato_missione(m, *settimana.get(m.chiave, (0, False))) for m in MISSIONI_SETTIMANA)
        + "\n\n**Di tutto il server** (premio a chi ha partecipato)\n"
        + "\n".join(righe_server)
    )
    return testo, pronto


async def _scheda_serie(guild_id: int, user_id: int) -> tuple[str, bool]:
    """(testo, promemoria acceso)."""
    serie, record, ultima, scudi, promemoria = await servizio.progressi_repo.serie_di(guild_id, user_id)
    adesso = servizio._adesso()
    attuale = serie_attuale(serie, ultima, scudi, adesso)
    righe = [
        f"Serie attuale: **{attuale}** giorni di fila con `/monete daily`. Record: **{record}**.",
        f"Se salti più di {SERIE_LIMITE_ORE} ore la serie si azzera. Ogni scudo copre un giorno saltato.",
        f"Scudi: **{scudi}/{SCUDI_MAX}** (costano {SCUDO_PREZZO} coin l'uno).",
    ]
    resta = scade_tra_ore(ultima, scudi, adesso) if attuale else None
    if resta is not None:
        righe.append(f"La serie si azzera tra circa {int(resta)} ore se non riscuoti.")
    tappa = prossima_tappa(attuale)
    righe.append(
        "Premi estetici: "
        + ", ".join(f"{t} giorni {PER_ID[o].emoji or '🎨'}" for t, o in sorted(PREMI_SERIE.items()))
        + (f". Prossimo tra {tappa - attuale} giorni." if tappa else ". Li hai presi tutti!")
    )
    righe.append("Promemoria privato 20 ore dopo la riscossione: **" + ("acceso" if promemoria else "spento") + "**.")
    return "\n".join(righe), promemoria


async def _scheda_pass(guild_id: int, user_id: int, booster: bool) -> tuple[str, int, bool]:
    """(testo, livelli da riscuotere, traccia premium aperta)."""
    chiave, _, fine = stagione_di(servizio._oggi())
    await servizio.svuota(guild_id, user_id)
    xp, liberi, premium_riscossi, premium = await servizio.progressi_repo.stato_pass(guild_id, user_id, chiave)
    from core.progressi_logic import livelli_raggiunti

    da_riscuotere = max(0, livelli_raggiunti(xp) - liberi) + (
        max(0, livelli_raggiunti(xp) - premium_riscossi) if premium else 0
    )
    return testo_pass(xp, liberi, premium_riscossi, premium, fine, booster), da_riscuotere, premium


# ---------------------------------------------------------------- la finestra
class VistaProgressi(BaseView):
    """Un menu per le sezioni e i bottoni di quella aperta. Lo usa solo chi l'ha aperta."""

    def __init__(self, autore_id: int, sezione: str, *, riscuotibile=False, premium=True, promemoria=False) -> None:
        super().__init__(timeout=300)
        self.autore_id = autore_id
        self.sezione = sezione
        menu = discord.ui.Select(
            placeholder="Cosa vuoi vedere?",
            options=[discord.SelectOption(label=nome, value=chiave, default=chiave == sezione) for chiave, nome in MENU],
        )
        menu.callback = self._scelta
        self.add_item(menu)
        if sezione in ("missioni", "pass"):
            self._bottone("Riscuoti", discord.ButtonStyle.success, self._riscuoti, disabled=not riscuotibile)
        if sezione == "pass" and not premium:
            self._bottone(f"Apri la traccia premium", discord.ButtonStyle.primary, self._apri_premium)
        if sezione == "serie":
            self._bottone(f"Compra uno scudo ({SCUDO_PREZZO})", discord.ButtonStyle.primary, self._scudo)
            self._bottone(
                "Spegni il promemoria" if promemoria else "Accendi il promemoria",
                discord.ButtonStyle.secondary,
                self._promemoria,
            )

    def _bottone(self, etichetta: str, stile, callback, disabled: bool = False) -> None:
        bottone = discord.ui.Button(label=etichetta, style=stile, disabled=disabled)
        bottone.callback = callback
        self.add_item(bottone)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        return interaction.user.id == self.autore_id

    async def _aggiorna(self, interaction: discord.Interaction, sezione: str, avviso: str | None = None) -> None:
        embed, vista = await costruisci(interaction.guild, interaction.user, sezione)
        await interaction.response.edit_message(embed=embed, view=vista)
        if avviso:
            await interaction.followup.send(avviso, ephemeral=True)

    async def _scelta(self, interaction: discord.Interaction) -> None:
        await self._aggiorna(interaction, interaction.data["values"][0])

    async def _riscuoti(self, interaction: discord.Interaction) -> None:
        guild, utente = interaction.guild, interaction.user
        if not await servizio.attivo(guild.id):
            await interaction.response.send_message(SPENTO, ephemeral=True)
            return
        if self.sezione == "missioni":
            esito = await servizio.riscatta_missioni(guild.id, utente.id)
            testo = f"🎁 Riscossi **{esito.monete}** coin ({esito.quanti} missioni)." + _testo_nuovi(esito.traguardi_nuovi)
            vuoto = esito.quanti == 0
        else:
            esito, nuovi = await servizio.riscatta_pass(guild.id, utente.id)
            livelli = esito.livelli_liberi + esito.livelli_premium
            testo = (
                f"🎁 Riscossi **{esito.monete}** coin ({livelli} premi del pass)."
                + _testo_oggetti(esito.oggetti) + _testo_nuovi(nuovi)
            )
            vuoto = esito.vuoto
        if vuoto:
            await interaction.response.send_message("Non c'è niente da riscuotere adesso.", ephemeral=True)
            return
        await self._aggiorna(interaction, self.sezione, testo)

    async def _apri_premium(self, interaction: discord.Interaction) -> None:
        guild, utente = interaction.guild, interaction.user
        if not await servizio.attivo(guild.id):
            await interaction.response.send_message(SPENTO, ephemeral=True)
            return
        booster = getattr(utente, "premium_since", None) is not None
        esito, nuovi = await servizio.sblocca_premium(guild.id, utente.id, booster)
        if esito == "saldo":
            await interaction.response.send_message(
                f"Servono {PASS_PREZZO_PREMIUM:,} coin, oppure il boost del server (gratis).", ephemeral=True
            )
            return
        if esito == "gia":
            await interaction.response.send_message("La traccia premium è già aperta.", ephemeral=True)
            return
        await self._aggiorna(
            interaction, "pass", "💎 Traccia premium aperta" + (" grazie al boost." if booster else ".") + _testo_nuovi(nuovi)
        )

    async def _scudo(self, interaction: discord.Interaction) -> None:
        guild, utente = interaction.guild, interaction.user
        if not await servizio.attivo(guild.id):
            await interaction.response.send_message(SPENTO, ephemeral=True)
            return
        esito = await servizio.compra_scudo(guild.id, utente.id)
        if esito == "pieno":
            await interaction.response.send_message(f"Hai già {SCUDI_MAX} scudi: è il massimo.", ephemeral=True)
        elif esito == "saldo":
            await interaction.response.send_message(f"Servono {SCUDO_PREZZO} coin.", ephemeral=True)
        else:
            await self._aggiorna(interaction, "serie", f"🛡️ Scudo comprato per {SCUDO_PREZZO} coin.")

    async def _promemoria(self, interaction: discord.Interaction) -> None:
        guild, utente = interaction.guild, interaction.user
        *_, acceso = await servizio.progressi_repo.serie_di(guild.id, utente.id)
        await servizio.imposta_promemoria(guild.id, utente.id, not acceso)
        await self._aggiorna(
            interaction, "serie",
            "Ti scriverò in privato 20 ore dopo la riscossione, se hai una serie da difendere."
            if not acceso else "Promemoria spento.",
        )


async def costruisci(guild: discord.Guild, utente: discord.abc.User, sezione: str) -> tuple[discord.Embed, VistaProgressi]:
    """L'embed della sezione e la finestra con i suoi bottoni."""
    colore = discord.Color.gold()
    if sezione == "globale":
        server, massimo, record, traguardi = await servizio.progressi_repo.profilo_globale(utente.id)
        testo = testo_profilo_globale(ProfiloGlobale(server, massimo, record, traguardi))
        return discord.Embed(title=TITOLI[sezione], description=testo, color=colore), VistaProgressi(utente.id, sezione)
    if not await servizio.attivo(guild.id):
        return discord.Embed(title=TITOLI[sezione], description=SPENTO, color=colore), VistaProgressi(utente.id, sezione)
    riscuotibile, premium, promemoria = False, True, False
    if sezione == "missioni":
        testo, riscuotibile = await _scheda_missioni(guild.id, utente.id)
    elif sezione == "traguardi":
        await servizio.valuta_traguardi(guild.id, utente.id)
        testo = testo_traguardi(await servizio.progressi_repo.traguardi_di(guild.id, utente.id))
    elif sezione == "serie":
        testo, promemoria = await _scheda_serie(guild.id, utente.id)
    else:
        booster = getattr(utente, "premium_since", None) is not None
        testo, da_riscuotere, premium = await _scheda_pass(guild.id, utente.id, booster)
        riscuotibile = da_riscuotere > 0
    embed = discord.Embed(title=TITOLI[sezione], description=testo[:4000], color=colore)
    return embed, VistaProgressi(utente.id, sezione, riscuotibile=riscuotibile, premium=premium, promemoria=promemoria)


class ProgressiCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        await super().cog_load()
        servizio.avvia(self.bot)

    async def cog_unload(self) -> None:
        await servizio.ferma()
        await super().cog_unload()

    @comando_di_gruppo(
        "level",
        nome="progressi",
        descrizione="Missioni, serie, traguardi e pass di 90 giorni, in un menu.",
    )
    async def progressi(self, interaction: discord.Interaction) -> None:
        if await _comando_rifiutato(interaction):
            return
        embed, vista = await costruisci(interaction.guild, interaction.user, "missioni")
        await interaction.response.send_message(embed=embed, view=vista, ephemeral=True)

    @comando_di_gruppo(
        "admin-livelli",
        nome="progressi",
        descrizione="Accende o spegne missioni, serie, traguardi e pass, e fissa l'obiettivo del server.",
    )
    @app_commands.describe(
        attivo="Sì per accenderli (i premi sono monete e oggetti), no per spegnerli",
        obiettivo_server=f"Messaggi della settimana per la missione di tutto il server ({OBIETTIVO_SERVER_MIN}-{OBIETTIVO_SERVER_MAX})",
    )
    async def progressi_staff(
        self,
        interaction: discord.Interaction,
        attivo: bool | None = None,
        obiettivo_server: app_commands.Range[int, OBIETTIVO_SERVER_MIN, OBIETTIVO_SERVER_MAX] | None = None,
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        guild = interaction.guild
        righe = []
        if attivo is not None:
            await servizio.imposta_attivo(guild.id, attivo, interaction.user.id)
            righe.append(
                "Missioni, serie, traguardi e pass sono **accesi**: si riscuotono con `/level progressi`."
                if attivo
                else "Missioni, serie, traguardi e pass sono **spenti**. I dati già raccolti restano."
            )
        if obiettivo_server is not None:
            await servizio.imposta_obiettivo_server(guild.id, obiettivo_server, interaction.user.id)
            righe.append(f"Missione di tutto il server: **{obiettivo_server}** messaggi a settimana.")
        if not righe:
            stato = "accesi" if await servizio.attivo(guild.id) else "spenti"
            righe.append(
                f"Sono **{stato}**. Obiettivo del server: **{await servizio.obiettivo_server_base(guild.id)}** messaggi a settimana."
            )
        await interaction.response.send_message("\n".join(righe), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ProgressiCog(bot))
