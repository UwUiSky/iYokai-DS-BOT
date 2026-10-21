"""
cogs/tickets/opzioni.py
=======================
Opzioni dei pannelli dei ticket e regole di apertura (catalogo #120): limiti, pausa,
orari, chi può aprire, nome e categorie del canale, avvisi, DM, permessi, squadra,
presa in carico, chiusura; lista nera, sospensione, staff reperibile; apertura da
comando (anche per conto di un utente o da un messaggio).
Comandi: `/ticket opzioni …` (admin), `/ticket lista-nera`, `/ticket sospendi` (admin),
`/ticket azzera-pausa`, `/ticket reperibile` (staff dei ticket), `/ticket apri`.
Le regole stanno in core/ticket_opzioni_logic.py; ogni opzione si salva da
ticket_opzioni_repo.imposta (D16).
Funzioni coperte: SPEC §13.14–§13.20
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from cogs.tickets.risposte import completa_pannelli
from cogs.tickets.tickets import (
    MODULE_TICKETS,
    SETTING_CATEGORY,
    ModuloTicket,
    _is_ticket_staff,
    _membro_staff,
    apri_da_comando,
)
from core import ticket_opzioni_logic as logica
from core.command_access import Livello, richiedi
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.repositories.ticket_form_repo import PannelloTicket, ticket_form_repo
from core.repositories.ticket_opzioni_repo import TroppeRegole, ticket_opzioni_repo
from core.role_safety import check_role_assignable

logger = logging.getLogger("iyokai.tickets.opzioni")

OPZIONI = ("opzioni", "Opzioni dei pannelli dei ticket (admin)")
MAX_ORE_SOSPENSIONE = 720
MAX_TESTO_COMANDO = logica.MAX_TESTO
NIENTE = discord.AllowedMentions.none()


async def completa_pannelli_pubblici(interaction: discord.Interaction, corrente: str):
    """Nomi dei pannelli per /ticket apri: li vede chiunque, come i bottoni dei pannelli."""
    if interaction.guild is None:
        return []
    pannelli = await ticket_form_repo.elenca_pannelli(interaction.guild.id)
    return [
        app_commands.Choice(name=p.name[:100], value=p.name[:100])
        for p in pannelli
        if corrente.strip().casefold() in p.name.casefold()
    ][:25]


def _ruoli_del_server(guild: discord.Guild, testo: str) -> tuple[int, ...]:
    """Gli ID di ruoli esistenti nel testo (mai @everyone). ValueError se uno non esiste."""
    ids = logica.leggi_ids(testo)
    mancanti = [i for i in ids if i == guild.id or guild.get_role(i) is None]
    if mancanti:
        raise ValueError(f"Il ruolo {mancanti[0]} non esiste in questo server (o è @everyone).")
    return ids


def _categorie_del_server(guild: discord.Guild, testo: str) -> tuple[int, ...]:
    ids = logica.leggi_ids(testo, massimo=5)
    for i in ids:
        if not isinstance(guild.get_channel(i), discord.CategoryChannel):
            raise ValueError(f"{i} non è una categoria di questo server.")
    return ids


def embed_opzioni(panel: PannelloTicket, o: logica.Opzioni) -> discord.Embed:
    embed = discord.Embed(title=f"Opzioni del pannello {panel.name}"[:256], color=discord.Color.blurple())
    for nome, valore in logica.riassunto(o):
        embed.add_field(name=nome, value=valore, inline=False)
    return embed


class TicketOpzioniCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ---------------------------------------------------------------- aiuti
    @staticmethod
    async def _pannello(interaction: discord.Interaction, nome: str) -> PannelloTicket | None:
        if interaction.guild is None:
            await interaction.response.send_message("Questo comando funziona solo in un server.", ephemeral=True)
            return None
        panel = await ticket_form_repo.pannello_per_nome(interaction.guild.id, nome.strip())
        if panel is None:
            await interaction.response.send_message(
                f"Nessun pannello chiamato **{nome.strip()[:100]}**.", ephemeral=True, allowed_mentions=NIENTE
            )
        return panel

    async def _salva(self, interaction: discord.Interaction, pannello: str, prepara) -> None:
        """Legge il pannello, chiama `prepara(guild)` -> dict delle opzioni da cambiare, salva e mostra."""
        panel = await self._pannello(interaction, pannello)
        if panel is None:
            return
        try:
            valori = prepara(interaction.guild)
        except ValueError as errore:
            await interaction.response.send_message(str(errore)[:2000], ephemeral=True, allowed_mentions=NIENTE)
            return
        opzioni = await ticket_opzioni_repo.imposta(panel.id, **valori)
        testo = "Opzioni salvate." if valori else "Nessuna opzione cambiata: ecco quelle attuali."
        await interaction.response.send_message(
            testo, embed=embed_opzioni(panel, opzioni), ephemeral=True, allowed_mentions=NIENTE
        )

    # ================================================================ /ticket opzioni …
    @comando_di_gruppo("ticket", nome="limiti", descrizione="Tetto di ticket aperti, pausa e ruoli esenti.", sottogruppo=OPZIONI)
    @richiedi(Livello.ADMIN)
    @app_commands.describe(
        pannello="Il pannello",
        massimo="Ticket aperti nel pannello (0 = senza tetto)",
        pausa_minuti="Minuti tra due aperture dello stesso utente (0 = nessuna)",
        esenti="Ruoli che saltano limiti, orari e sospensione (o «nessuno»)",
    )
    @app_commands.autocomplete(pannello=completa_pannelli)
    async def limiti(
        self,
        interaction: discord.Interaction,
        pannello: app_commands.Range[str, 1, 50],
        massimo: app_commands.Range[int, 0, logica.MAX_APERTI_PANNELLO] | None = None,
        pausa_minuti: app_commands.Range[int, 0, logica.MAX_PAUSA_SECONDI // 60] | None = None,
        esenti: app_commands.Range[str, 1, 500] | None = None,
    ) -> None:
        def prepara(guild):
            valori = {}
            if massimo is not None:
                valori["max_aperti"] = massimo or None
            if pausa_minuti is not None:
                valori["pausa_secondi"] = pausa_minuti * 60
            if esenti is not None:
                valori["ruoli_esenti"] = _ruoli_del_server(guild, esenti)
            return valori

        await self._salva(interaction, pannello, prepara)

    @comando_di_gruppo("ticket", nome="orari", descrizione="Orari di apertura e cosa succede fuori orario.", sottogruppo=OPZIONI)
    @richiedi(Livello.ADMIN)
    @app_commands.describe(
        pannello="Il pannello",
        orari="Es. «lun-ven 09:00-18:00; sab 10:00-12:00» (o «nessuno»)",
        fuso="Fuso orario, es. Europe/Rome",
        messaggio="Cosa leggere fuori orario (o «nessuno»)",
        apri_lo_stesso="Fuori orario il ticket si apre con un avviso",
    )
    @app_commands.autocomplete(pannello=completa_pannelli)
    async def orari(
        self,
        interaction: discord.Interaction,
        pannello: app_commands.Range[str, 1, 50],
        orari: app_commands.Range[str, 1, 300] | None = None,
        fuso: app_commands.Range[str, 1, 50] | None = None,
        messaggio: app_commands.Range[str, 1, MAX_TESTO_COMANDO] | None = None,
        apri_lo_stesso: bool | None = None,
    ) -> None:
        def prepara(guild):
            valori = {}
            if orari is not None:
                spento = orari.strip().lower() == "nessuno"
                if not spento:
                    logica.leggi_orari(orari)
                valori["orari"] = None if spento else orari.strip()
            if fuso is not None:
                logica.fuso_valido(fuso.strip())
                valori["fuso"] = fuso.strip()
            if messaggio is not None:
                valori["fuori_orario_testo"] = logica.controlla_testo(messaggio)
            if apri_lo_stesso is not None:
                valori["fuori_orario_apri"] = apri_lo_stesso
            return valori

        await self._salva(interaction, pannello, prepara)

    @comando_di_gruppo("ticket", nome="accesso", descrizione="Chi può aprire: regole per ruolo, lette dall'alto.", sottogruppo=OPZIONI)
    @richiedi(Livello.ADMIN)
    @app_commands.describe(pannello="Il pannello", ruolo="Il ruolo", regola="Permetti, nega o togli la regola")
    @app_commands.choices(
        regola=[app_commands.Choice(name=n, value=n) for n in ("permetti", "nega", "togli")]
    )
    @app_commands.autocomplete(pannello=completa_pannelli)
    async def accesso(
        self,
        interaction: discord.Interaction,
        pannello: app_commands.Range[str, 1, 50],
        ruolo: discord.Role,
        regola: app_commands.Choice[str],
    ) -> None:
        panel = await self._pannello(interaction, pannello)
        if panel is None:
            return
        permetti = {"permetti": True, "nega": False}.get(regola.value)
        try:
            regole = await ticket_opzioni_repo.imposta_regola(panel.id, ruolo.id, permetti)
        except TroppeRegole:
            await interaction.response.send_message(
                f"Il pannello ha già {logica.MAX_REGOLE_ACCESSO} regole: togline una.", ephemeral=True
            )
            return
        righe = [f"{i + 1}. <@&{rid}> → {'permetti' if p else 'nega'}" for i, (rid, p) in enumerate(regole)]
        await interaction.response.send_message(
            "Regole di accesso (la prima che tocca un ruolo dell'utente decide; nessuna = tutti possono aprire):\n"
            + ("\n".join(righe) or "nessuna"),
            ephemeral=True,
            allowed_mentions=NIENTE,
        )

    @comando_di_gruppo("ticket", nome="canale", descrizione="Nome del canale e categorie di riserva.", sottogruppo=OPZIONI)
    @richiedi(Livello.ADMIN)
    @app_commands.describe(
        pannello="Il pannello",
        nome="Modello: {numero} {num} {utente} {nickname} (o «nessuno»)",
        riserva="Fino a 5 categorie se la principale è piena (o «nessuno»)",
    )
    @app_commands.autocomplete(pannello=completa_pannelli)
    async def canale(
        self,
        interaction: discord.Interaction,
        pannello: app_commands.Range[str, 1, 50],
        nome: app_commands.Range[str, 1, logica.MAX_NOME_CANALE] | None = None,
        riserva: app_commands.Range[str, 1, 300] | None = None,
    ) -> None:
        def prepara(guild):
            valori = {}
            if nome is not None:
                spento = nome.strip().lower() == "nessuno"
                valori["nome_modello"] = None if spento else logica.controlla_modello_nome(nome)
            if riserva is not None:
                valori["categorie_riserva"] = _categorie_del_server(guild, riserva)
            return valori

        await self._salva(interaction, pannello, prepara)

    @comando_di_gruppo("ticket", nome="avvisi", descrizione="Chi avvisare all'apertura e primo messaggio fissato.", sottogruppo=OPZIONI)
    @richiedi(Livello.ADMIN)
    @app_commands.describe(
        pannello="Il pannello",
        ruoli="Ruoli da chiamare (o «nessuno»)",
        here="Chiama anche @here",
        cancella="Cancella il ping subito dopo",
        fissa="Fissa il primo messaggio del ticket",
    )
    @app_commands.autocomplete(pannello=completa_pannelli)
    async def avvisi(
        self,
        interaction: discord.Interaction,
        pannello: app_commands.Range[str, 1, 50],
        ruoli: app_commands.Range[str, 1, 500] | None = None,
        here: bool | None = None,
        cancella: bool | None = None,
        fissa: bool | None = None,
    ) -> None:
        def prepara(guild):
            valori = {}
            if ruoli is not None:
                valori["ping_ruoli"] = _ruoli_del_server(guild, ruoli)
            for chiave, valore in (("ping_here", here), ("ping_cancella", cancella), ("fissa_primo", fissa)):
                if valore is not None:
                    valori[chiave] = valore
            return valori

        await self._salva(interaction, pannello, prepara)

    @comando_di_gruppo("ticket", nome="messaggi", descrizione="DM all'utente e testi di presa e rilascio.", sottogruppo=OPZIONI)
    @richiedi(Livello.ADMIN)
    @app_commands.describe(
        pannello="Il pannello",
        dm_apertura="DM all'apertura: {utente} {server} {numero} (o «nessuno»)",
        dm_chiusura="DM alla chiusura (o «nessuno»)",
        presa="Testo alla presa in carico, anche {staff} (o «nessuno»)",
        rilascio="Testo al rilascio (o «nessuno»)",
        transcript_dm="Manda il transcript in DM all'utente",
    )
    @app_commands.autocomplete(pannello=completa_pannelli)
    async def messaggi(
        self,
        interaction: discord.Interaction,
        pannello: app_commands.Range[str, 1, 50],
        dm_apertura: app_commands.Range[str, 1, MAX_TESTO_COMANDO] | None = None,
        dm_chiusura: app_commands.Range[str, 1, MAX_TESTO_COMANDO] | None = None,
        presa: app_commands.Range[str, 1, MAX_TESTO_COMANDO] | None = None,
        rilascio: app_commands.Range[str, 1, MAX_TESTO_COMANDO] | None = None,
        transcript_dm: bool | None = None,
    ) -> None:
        def prepara(guild):
            valori = {}
            for chiave, testo in (
                ("dm_apertura", dm_apertura), ("dm_chiusura", dm_chiusura),
                ("testo_presa", presa), ("testo_rilascio", rilascio),
            ):
                if testo is not None:
                    valori[chiave] = logica.controlla_testo(testo)
            if transcript_dm is not None:
                valori["transcript_dm"] = transcript_dm
            return valori

        await self._salva(interaction, pannello, prepara)

    @comando_di_gruppo("ticket", nome="permessi", descrizione="Permessi dell'utente, osservatori, ruoli durante, squadra.", sottogruppo=OPZIONI)
    @richiedi(Livello.ADMIN)
    @app_commands.describe(
        pannello="Il pannello",
        togli="Tolti all'utente: allegati, link, reazioni, emoji, vocali (o «nessuno»)",
        osservatori="Ruoli che vedono e non scrivono (o «nessuno»)",
        durante="Ruoli dati all'utente finché il ticket è aperto (o «nessuno»)",
        squadra="Staff di questo pannello al posto del supporto (o «nessuno»)",
    )
    @app_commands.autocomplete(pannello=completa_pannelli)
    async def permessi(
        self,
        interaction: discord.Interaction,
        pannello: app_commands.Range[str, 1, 50],
        togli: app_commands.Range[str, 1, 100] | None = None,
        osservatori: app_commands.Range[str, 1, 500] | None = None,
        durante: app_commands.Range[str, 1, 500] | None = None,
        squadra: app_commands.Range[str, 1, 500] | None = None,
    ) -> None:
        def prepara(guild):
            valori = {}
            if togli is not None:
                valori["permessi_negati"] = logica.leggi_permessi_negati(togli)
            for chiave, testo in (("ruoli_osservatori", osservatori), ("ruoli_durante", durante), ("ruoli_staff", squadra)):
                if testo is not None:
                    valori[chiave] = _ruoli_del_server(guild, testo)
            if durante is not None:
                # Chi apre un ticket prende questi ruoli da solo: stesse regole dei ruoli auto-assegnabili.
                for r in valori["ruoli_durante"]:
                    motivo = check_role_assignable(guild, guild.get_role(r), interaction.user, self_service=True)
                    if motivo:
                        raise ValueError(f"<@&{r}>: {motivo}")
            return valori

        await self._salva(interaction, pannello, prepara)

    @comando_di_gruppo("ticket", nome="presa", descrizione="Presa in carico: categoria, esclusiva, assegnazione automatica.", sottogruppo=OPZIONI)
    @richiedi(Livello.ADMIN)
    @app_commands.describe(
        pannello="Il pannello",
        categoria="Dove spostare i ticket presi in carico",
        togli_categoria="Non spostarli più",
        esclusiva="Dopo la presa gli altri dello staff…",
        automatica="Il primo dello staff che risponde lo prende in carico",
    )
    @app_commands.choices(
        esclusiva=[
            app_commands.Choice(name="scrivono e vedono", value="no"),
            app_commands.Choice(name="vedono ma non scrivono", value="scrivere"),
            app_commands.Choice(name="non vedono", value="vedere"),
        ]
    )
    @app_commands.autocomplete(pannello=completa_pannelli)
    async def presa(
        self,
        interaction: discord.Interaction,
        pannello: app_commands.Range[str, 1, 50],
        categoria: discord.CategoryChannel | None = None,
        togli_categoria: bool | None = None,
        esclusiva: app_commands.Choice[str] | None = None,
        automatica: bool | None = None,
    ) -> None:
        def prepara(guild):
            valori = {}
            if categoria is not None:
                valori["categoria_presi"] = categoria.id
            if togli_categoria:
                valori["categoria_presi"] = None
            if esclusiva is not None:
                valori["claim_esclusivo"] = esclusiva.value
            if automatica is not None:
                valori["assegna_auto"] = automatica
            return valori

        await self._salva(interaction, pannello, prepara)

    @comando_di_gruppo("ticket", nome="chiusura", descrizione="Conferma prima di chiudere e chi può chiudere.", sottogruppo=OPZIONI)
    @richiedi(Livello.ADMIN)
    @app_commands.describe(
        pannello="Il pannello",
        conferma="Chiedi conferma prima di chiudere",
        utente_chiude="Chi ha aperto il ticket può chiuderlo",
    )
    @app_commands.autocomplete(pannello=completa_pannelli)
    async def chiusura(
        self,
        interaction: discord.Interaction,
        pannello: app_commands.Range[str, 1, 50],
        conferma: bool | None = None,
        utente_chiude: bool | None = None,
    ) -> None:
        def prepara(guild):
            valori = {}
            if conferma is not None:
                valori["conferma_chiusura"] = conferma
            if utente_chiude is not None:
                valori["utente_chiude"] = utente_chiude
            return valori

        await self._salva(interaction, pannello, prepara)

    @comando_di_gruppo("ticket", nome="mostra", descrizione="Tutte le opzioni di un pannello.", sottogruppo=OPZIONI)
    @richiedi(Livello.ADMIN)
    @app_commands.describe(pannello="Il pannello")
    @app_commands.autocomplete(pannello=completa_pannelli)
    async def mostra(self, interaction: discord.Interaction, pannello: app_commands.Range[str, 1, 50]) -> None:
        await self._salva(interaction, pannello, lambda guild: {})

    # ================================================================ regole del server
    @comando_di_gruppo("ticket", nome="lista-nera", descrizione="Utenti e ruoli che non possono aprire ticket.")
    @richiedi(Livello.ADMIN)
    @app_commands.describe(
        azione="Aggiungi, togli o mostra",
        utente="L'utente (anche uscito: scrivi il suo ID)",
        ruolo="Oppure un ruolo",
        motivo="Perché (facoltativo)",
    )
    @app_commands.choices(azione=[app_commands.Choice(name=n, value=n) for n in ("aggiungi", "togli", "mostra")])
    async def lista_nera(
        self,
        interaction: discord.Interaction,
        azione: app_commands.Choice[str],
        utente: discord.User | None = None,
        ruolo: discord.Role | None = None,
        motivo: app_commands.Range[str, 1, 200] | None = None,
    ) -> None:
        guild = interaction.guild
        if azione.value == "mostra":
            righe = [
                f"{'<@&' if is_role else '<@'}{tid}> {('— ' + m) if m else ''}"
                for tid, is_role, m in await ticket_opzioni_repo.lista_nera(guild.id)
            ]
            await interaction.response.send_message(
                ("Lista nera dei ticket (le 25 più recenti):\n" + "\n".join(righe))[:2000] if righe else "La lista nera è vuota.",
                ephemeral=True, allowed_mentions=NIENTE,
            )
            return
        if (utente is None) == (ruolo is None) or (ruolo is not None and ruolo.id == guild.id):
            await interaction.response.send_message("Scegli un utente oppure un ruolo (non @everyone).", ephemeral=True)
            return
        bersaglio = utente or ruolo
        if azione.value == "togli":
            tolto = await ticket_opzioni_repo.sblocca(guild.id, bersaglio.id)
            testo = f"{bersaglio.mention} può di nuovo aprire ticket." if tolto else f"{bersaglio.mention} non era in lista nera."
        else:
            if utente is not None and (utente.id == interaction.user.id or utente.bot):
                await interaction.response.send_message("Non puoi mettere in lista nera te stesso o un bot.", ephemeral=True)
                return
            try:
                await ticket_opzioni_repo.blocca(guild.id, bersaglio.id, ruolo is not None, motivo, interaction.user.id)
            except TroppeRegole:
                await interaction.response.send_message(
                    f"La lista nera ha già {logica.MAX_LISTA_NERA} voci: togline qualcuna.", ephemeral=True
                )
                return
            testo = f"{bersaglio.mention} non può più aprire ticket. Lo staff resta escluso dal blocco."
        await interaction.response.send_message(testo, ephemeral=True, allowed_mentions=NIENTE)

    @comando_di_gruppo("ticket", nome="sospendi", descrizione="Sospendi l'apertura dei ticket (senza motivo: riprendi).")
    @richiedi(Livello.ADMIN)
    @app_commands.describe(motivo="Il motivo mostrato a chi prova ad aprire", ore="Per quante ore (vuoto = finché non riprendi)")
    async def sospendi(
        self,
        interaction: discord.Interaction,
        motivo: app_commands.Range[str, 1, 300] | None = None,
        ore: app_commands.Range[int, 1, MAX_ORE_SOSPENSIONE] | None = None,
    ) -> None:
        guild = interaction.guild
        if motivo is None:
            ripreso = await ticket_opzioni_repo.riprendi(guild.id)
            await interaction.response.send_message(
                "Apertura dei ticket ripresa." if ripreso else "L'apertura dei ticket non era sospesa.", ephemeral=True
            )
            return
        fino = datetime.now(timezone.utc) + timedelta(hours=ore) if ore else None
        await ticket_opzioni_repo.sospendi(guild.id, motivo, fino, interaction.user.id)
        quando = f" fino al <t:{int(fino.timestamp())}:f>" if fino else " finché non usi di nuovo questo comando senza motivo"
        await interaction.response.send_message(
            f"Apertura dei ticket sospesa{quando}. I ruoli esenti e lo staff possono aprire.", ephemeral=True
        )

    @comando_di_gruppo("ticket", nome="azzera-pausa", descrizione="Togli la pausa tra due ticket a un utente.")
    @app_commands.describe(utente="L'utente")
    async def azzera_pausa(self, interaction: discord.Interaction, utente: discord.Member) -> None:
        if not await _is_ticket_staff(interaction):
            await interaction.response.send_message("Solo lo staff dei ticket può farlo.", ephemeral=True)
            return
        await ticket_opzioni_repo.azzera_pausa(interaction.guild.id, utente.id)
        await interaction.response.send_message(
            f"{utente.mention} può aprire subito un altro ticket.", ephemeral=True, allowed_mentions=NIENTE
        )

    @comando_di_gruppo("ticket", nome="reperibile", descrizione="Entra o esci dallo staff avvisato a ogni nuovo ticket.")
    async def reperibile(self, interaction: discord.Interaction) -> None:
        if not await _is_ticket_staff(interaction):
            await interaction.response.send_message("Solo lo staff dei ticket può farlo.", ephemeral=True)
            return
        esito = await ticket_opzioni_repo.cambia_reperibile(interaction.guild.id, interaction.user.id)
        testo = {
            True: "Sei reperibile: ti aggiungo e ti avviso a ogni nuovo ticket. Rilancia il comando per smettere.",
            False: "Non sei più reperibile.",
            None: f"Ci sono già {logica.MAX_REPERIBILI} reperibili in questo server.",
        }[esito]
        await interaction.response.send_message(testo, ephemeral=True)

    # ================================================================ apertura da comando
    @comando_di_gruppo("ticket", nome="apri", descrizione="Apri un ticket (lo staff anche per un utente o da un messaggio).")
    @app_commands.describe(
        pannello="Il pannello (vuoto = ticket classico)",
        motivo="Di cosa hai bisogno",
        utente="Solo staff: apri il ticket per questo utente",
        messaggio="Link di un messaggio da citare nel ticket",
        aggiungi_autore="Solo staff: aggiungi al ticket l'autore del messaggio",
    )
    @app_commands.autocomplete(pannello=completa_pannelli_pubblici)
    async def apri(
        self,
        interaction: discord.Interaction,
        pannello: app_commands.Range[str, 1, 50] | None = None,
        motivo: app_commands.Range[str, 1, 512] | None = None,
        utente: discord.Member | None = None,
        messaggio: app_commands.Range[str, 1, 200] | None = None,
        aggiungi_autore: bool = False,
    ) -> None:
        guild = interaction.guild
        if guild is None or not await db.is_module_active_for_guild(guild.id, MODULE_TICKETS):
            await interaction.response.send_message("Il sistema di ticket non è attivo su questo server.", ephemeral=True)
            return
        panel = None
        if pannello is not None:
            panel = await self._pannello(interaction, pannello)
            if panel is None:
                return
            category = guild.get_channel(panel.category_id)
        else:
            category_id = await db.get_guild_setting(guild.id, SETTING_CATEGORY)
            category = guild.get_channel(category_id) if category_id else None
        if not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message(
                "Manca la categoria dei ticket: scegli un pannello o chiedi a un amministratore.", ephemeral=True
            )
            return
        staff = await _membro_staff(interaction.user, guild.id, panel.id if panel else None)
        if (utente is not None or aggiungi_autore) and not staff:
            await interaction.response.send_message(
                "Solo lo staff dei ticket può aprire per un altro utente o aggiungere l'autore del messaggio.",
                ephemeral=True,
            )
            return
        if utente is not None and utente.bot:
            await interaction.response.send_message("Non si apre un ticket per un bot.", ephemeral=True)
            return
        dati = {
            "motivo": motivo,
            "link": messaggio,
            "utente": utente if utente is not None and utente.id != interaction.user.id else None,
            "aggiungi_autore": aggiungi_autore,
        }
        if panel is not None and dati["utente"] is None:
            domande = await ticket_form_repo.elenca_domande(panel.id)
            if domande:
                # La finestra deve essere la prima risposta: motivo e messaggio la seguono.
                await interaction.response.send_modal(ModuloTicket(panel, domande, comando=dati))
                return
        await interaction.response.defer(ephemeral=True)
        await apri_da_comando(interaction, guild, category, panel, **dati)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TicketOpzioniCog(bot))
