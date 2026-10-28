"""
cogs/automod/parole_odio.py
===========================
Parole vietate con varianti (AMD-014): comandi di `/automod odio` per la lista
di base, le parole proprie e quelle lecite, e controllo dei nomi (nickname e
nome visualizzato) all'ingresso e al cambio. Il controllo dei messaggi sta in
cogs/automod/automod.py; il filtro in core/automod_parole_logic.py.
Il blocco preventivo con l'AutoMod nativo, i richiami e la libreria mondiale delle
parole (D35) hanno comandi qui; la parte che parla con Discord sta in
core/automod_odio_azioni.py.
Funzioni coperte: SPEC §6 (AMD-014, D35)
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from cogs.automod.automod import MODULE_AUTOMOD, is_member_exempt
from core.automod_odio_azioni import sincronizza_blocco
from cogs.moderation._shared import ensure_module_enabled
from core import automod_parole_opzioni as opzioni_parole
from core import channel_router as router
from core import odio_opzioni
from core.config import config
from core.odio_libreria_logic import STATI, STATO_APPROVATA, STATO_CANDIDATA, STATO_RIFIUTATA, pulisci_lingua, pulisci_variante
from core.repositories.odio_libreria_repo import odio_libreria_repo
from core.odio_libreria_service import libreria_odio
from core.automod_parole_logic import Filtro, normalizza, trova
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.repositories.automod_advanced_repo import automod_advanced_repo

NOME_SOSTITUTIVO = "Nome rimosso"
MAX_PROVA = 400
SOTTOGRUPPO = ("odio", "Parole vietate con varianti e insulti d'odio.")

LISTE = [
    app_commands.Choice(name="parole proprie del server", value=opzioni_parole.LISTA_PROPRIE),
    app_commands.Choice(name="parole lecite", value=opzioni_parole.LISTA_LECITE),
]
AZIONI_LIBRERIA = [
    app_commands.Choice(name="elenca", value="elenca"),
    app_commands.Choice(name="approva", value="approva"),
    app_commands.Choice(name="rifiuta", value="rifiuta"),
    app_commands.Choice(name="aggiungi", value="aggiungi"),
]
AZIONI = [
    app_commands.Choice(name="aggiungi", value="aggiungi"),
    app_commands.Choice(name="rimuovi", value="rimuovi"),
]


def nuovo_nick(nick: str | None, nome_base: str, filtro: Filtro) -> tuple[bool, str | None]:
    """
    (cambiare?, nickname nuovo). `nome_base` è il nome senza nickname (nome
    visualizzato o utente). Nickname vietato: via il nickname, e se anche il
    nome di base è vietato un nome neutro. Nickname assente o pulito: si
    cambia solo se il nome di base è vietato e non c'è nickname.
    """
    base_vietato = trova(nome_base, filtro) is not None
    if nick:
        if trova(nick, filtro) is None:
            return False, None
        return True, NOME_SOSTITUTIVO if base_vietato else None
    return (True, NOME_SOSTITUTIVO) if base_vietato else (False, None)


async def controlla_nome(membro: discord.Member) -> str | None:
    """
    Ripulisce il nome del membro se contiene una parola vietata. Restituisce
    cosa è stato fatto (per il log) o None. Rispetta moduli ed esenzioni.
    """
    guild = membro.guild
    if membro.bot or guild.owner_id == membro.id:
        return None
    if not await db.is_module_active_for_guild(guild.id, MODULE_AUTOMOD):
        return None
    filtro, opz = await opzioni_parole.filtro_del_server(guild.id)
    if not opz.nick or filtro.vuoto():
        return None
    impostazioni = await automod_advanced_repo.get_settings(guild.id)
    if is_member_exempt(membro, impostazioni, 0):
        return None
    cambia, nick = nuovo_nick(membro.nick, membro.global_name or membro.name, filtro)
    if not cambia or nick == membro.nick:  # stesso nome: niente cambio, niente giro di eventi
        return None
    try:
        await membro.edit(nick=nick, reason="AutoMod: nome con parola vietata")
        esito = "nickname azzerato" if nick is None else f"nickname cambiato in «{nick}»"
    except (discord.Forbidden, discord.HTTPException):
        esito = "non riuscito (permessi o gerarchia)"
    canale = await router.destinazione(guild, router.TIPO_AUTOMOD, impostazioni.log_channel_id)
    if canale is not None:
        embed = discord.Embed(title="🛡️ AutoMod — Nome con parola vietata", color=discord.Color.orange())
        embed.add_field(name="Utente", value=f"{membro.mention} ({membro.id})", inline=False)
        embed.add_field(name="Azione", value=esito, inline=False)
        await router.invia_a(canale, guild, router.TIPO_AUTOMOD, embed=embed)
    return esito


class ParoleOdioCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, membro: discord.Member) -> None:
        await controlla_nome(membro)

    @commands.Cog.listener()
    async def on_member_update(self, prima: discord.Member, dopo: discord.Member) -> None:
        if prima.nick != dopo.nick:
            await controlla_nome(dopo)

    @commands.Cog.listener()
    async def on_user_update(self, prima: discord.User, dopo: discord.User) -> None:
        if prima.global_name == dopo.global_name and prima.name == dopo.name:
            return
        for guild in dopo.mutual_guilds:
            membro = guild.get_member(dopo.id)
            if membro is not None:
                await controlla_nome(membro)

    # ================================================================
    # Comandi
    # ================================================================
    @comando_di_gruppo(
        "automod", nome="stato", descrizione="Mostra come sono impostate le parole vietate.", sottogruppo=SOTTOGRUPPO
    )
    async def stato(self, interaction: discord.Interaction) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        o = await opzioni_parole.leggi(interaction.guild.id)
        od = await odio_opzioni.leggi(interaction.guild.id)
        righe = [
            f"**Lista di base** (insulti d'odio, italiano e inglese): {'accesa' if o.base else 'SPENTA'}",
            f"**Parole proprie**: {len(o.proprie)}",
            f"**Parole lecite**: {len(o.lecite)}",
            f"**Controllo dei nomi**: {'acceso' if o.nick else 'spento'}",
            f"**Blocco preventivo (AutoMod di Discord)**: {'acceso' if od.blocco else 'spento'}",
            f"**Richiami**: {od.soglia} in {od.minuti} minuti, poi timeout di {od.timeout_minuti} minuti",
        ]
        await interaction.response.send_message("\n".join(righe), ephemeral=True)

    @comando_di_gruppo(
        "automod", nome="base", descrizione="Accende o spegne la lista di base degli insulti d'odio.",
        sottogruppo=SOTTOGRUPPO,
    )
    @app_commands.describe(attiva="Accesa o spenta", conferma="Serve per spegnerla: scrivi true")
    async def base(self, interaction: discord.Interaction, attiva: bool, conferma: bool = False) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        try:
            await opzioni_parole.imposta_base(interaction.guild.id, attiva, conferma, interaction.user.id)
        except ValueError as errore:
            await interaction.response.send_message(f"{errore} Rilancia il comando con `conferma: true`.", ephemeral=True)
            return
        await interaction.response.send_message(
            "Lista di base accesa." if attiva else "Lista di base spenta: gli insulti d'odio non sono più bloccati.",
            ephemeral=True,
        )

    @comando_di_gruppo(
        "automod", nome="parola", descrizione="Aggiunge o toglie una parola propria o una parola lecita.",
        sottogruppo=SOTTOGRUPPO,
    )
    @app_commands.describe(
        lista="Quale lista", azione="Aggiungi o rimuovi",
        testo="La parola (da 3 a 60 caratteri): vale anche con cifre, accenti e lettere separate",
    )
    @app_commands.choices(lista=LISTE, azione=AZIONI)
    async def parola(
        self,
        interaction: discord.Interaction,
        lista: app_commands.Choice[str],
        azione: app_commands.Choice[str],
        testo: app_commands.Range[str, 3, opzioni_parole.MAX_LUNGHEZZA_VOCE],
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        guild_id, autore = interaction.guild.id, interaction.user.id
        try:
            if azione.value == "aggiungi":
                fatto = await opzioni_parole.aggiungi_voce(guild_id, lista.value, testo, autore)
                messaggio = "Parola aggiunta." if fatto else "C'era già."
            else:
                fatto = await opzioni_parole.rimuovi_voce(guild_id, lista.value, testo, autore)
                messaggio = "Parola rimossa." if fatto else "Non c'era in lista."
        except ValueError as errore:
            messaggio = str(errore)
        await interaction.response.send_message(messaggio, ephemeral=True)

    @comando_di_gruppo(
        "automod", nome="nomi", descrizione="Controlla nickname e nomi visualizzati all'ingresso e al cambio.",
        sottogruppo=SOTTOGRUPPO,
    )
    @app_commands.describe(attiva="Acceso o spento")
    async def nomi(self, interaction: discord.Interaction, attiva: bool) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        await opzioni_parole.imposta_nick(interaction.guild.id, attiva, interaction.user.id)
        await interaction.response.send_message(
            "Controllo dei nomi acceso." if attiva else "Controllo dei nomi spento.", ephemeral=True
        )

    @comando_di_gruppo(
        "automod", nome="blocco", descrizione="Blocco preventivo delle frasi d'odio.",
        sottogruppo=SOTTOGRUPPO,
    )
    @app_commands.describe(
        attivo="Acceso o spento",
        messaggio="Testo del blocco (max 150); «-» = predefinito",
    )
    async def blocco(
        self,
        interaction: discord.Interaction,
        attivo: bool | None = None,
        messaggio: app_commands.Range[str, 1, odio_opzioni.MAX_MESSAGGIO] | None = None,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        await interaction.response.defer(ephemeral=True)
        testo = None if messaggio is None else ("" if messaggio.strip() == "-" else messaggio)
        await odio_opzioni.imposta_blocco(interaction.guild.id, attivo, testo, interaction.user.id)
        opz = await odio_opzioni.leggi(interaction.guild.id)
        riuscito, avviso = await sincronizza_blocco(interaction.guild, opz)
        if attivo and not riuscito:  # su Discord la regola non c'e': l'impostazione non resta accesa
            await odio_opzioni.imposta_blocco(interaction.guild.id, False, None, interaction.user.id)
            opz = await odio_opzioni.leggi(interaction.guild.id)
        stato = "NON acceso" if attivo and not riuscito else ("acceso" if opz.blocco else "spento")
        riga = f"Blocco preventivo {stato}. Testo: «{opz.messaggio}»"
        await interaction.followup.send(f"{riga}\n{avviso}" if avviso else riga, ephemeral=True)

    @comando_di_gruppo(
        "automod", nome="richiami", descrizione="Richiami per parole d'odio prima del timeout.",
        sottogruppo=SOTTOGRUPPO,
    )
    @app_commands.describe(
        richiami="Quanti (3)", minuti="In quanti minuti (60)", timeout="Minuti di timeout (60)",
    )
    async def richiami(
        self,
        interaction: discord.Interaction,
        richiami: app_commands.Range[int, 1, odio_opzioni.MAX_SOGLIA] | None = None,
        minuti: app_commands.Range[int, 1, odio_opzioni.MAX_MINUTI] | None = None,
        timeout: app_commands.Range[int, 1, odio_opzioni.MAX_TIMEOUT_MINUTI] | None = None,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        await odio_opzioni.imposta_richiami(interaction.guild.id, richiami, minuti, timeout, interaction.user.id)
        o = await odio_opzioni.leggi(interaction.guild.id)
        await interaction.response.send_message(
            f"{o.soglia} richiami in {o.minuti} minuti portano a un timeout di {o.timeout_minuti} minuti.", ephemeral=True
        )

    @comando_di_gruppo(
        "automod", nome="libreria", descrizione="Solo proprietario del bot: libreria delle parole.",
        sottogruppo=SOTTOGRUPPO,
    )
    @app_commands.describe(azione="Cosa fare", testo="La variante", lingua="Lingua, es. it")
    @app_commands.choices(azione=AZIONI_LIBRERIA)
    async def libreria(
        self,
        interaction: discord.Interaction,
        azione: app_commands.Choice[str],
        testo: app_commands.Range[str, 3, opzioni_parole.MAX_LUNGHEZZA_VOCE] | None = None,
        lingua: app_commands.Range[str, 2, 8] | None = None,
    ) -> None:
        if interaction.user.id != config.OWNER_ID:
            await interaction.response.send_message("Solo il proprietario del bot può usare questo comando.", ephemeral=True)
            return
        await interaction.response.send_message(await self._libreria(azione.value, testo, lingua), ephemeral=True)

    @staticmethod
    async def _libreria(azione: str, testo: str | None, lingua: str | None) -> str:
        if azione == "elenca":
            conti = await odio_libreria_repo.conta_per_stato()
            candidate = await odio_libreria_repo.elenca(STATO_CANDIDATA, 25)
            righe = [f"{s}: {conti.get(s, 0)}" for s in STATI]
            righe += [f"`{p.variante.replace(chr(96), '')}` ({p.lingua or '?'}) — {p.server} server" for p in candidate]
            return "\n".join(righe)[:1900]
        variante = pulisci_variante(testo or "")
        if variante is None:
            return "Serve una variante di 1 o 2 parole, da 3 a 60 caratteri."
        if azione == "aggiungi":
            await odio_libreria_repo.aggiungi_base(variante, pulisci_lingua(lingua or ""))
            libreria_odio.svuota()
            return "Aggiunta: vale subito in tutti i server."
        stato = STATO_APPROVATA if azione == "approva" else STATO_RIFIUTATA
        if not await odio_libreria_repo.imposta_stato(variante, stato):
            return "Questa variante non è in libreria."
        libreria_odio.svuota()
        return "Approvata: vale in tutti i server." if stato == STATO_APPROVATA else "Rifiutata: non varrà mai in nessun server."

    @comando_di_gruppo(
        "automod", nome="prova", descrizione="Prova un testo contro le parole vietate, senza agire.",
        sottogruppo=SOTTOGRUPPO,
    )
    @app_commands.describe(testo="Il testo da provare")
    async def prova(
        self, interaction: discord.Interaction, testo: app_commands.Range[str, 1, MAX_PROVA]
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        trovato = await opzioni_parole.trova_nel_testo(interaction.guild.id, testo)
        letto = normalizza(testo).replace("`", "")[:300]
        if trovato is None:
            esito = "Nessuna parola vietata."
        else:
            esito = f"Scatterebbe: voce `{trovato.voce.replace('`', '')}` (modo: {trovato.modo})."
        await interaction.response.send_message(f"{esito}\nTesto letto dal filtro: `{letto}`", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ParoleOdioCog(bot))
