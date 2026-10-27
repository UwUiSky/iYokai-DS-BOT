"""
cogs/ai/config.py
=================
Il gruppo `/ai` (D26): consenso e interruttore del server, canali spenti,
limiti e tetto di spesa, privacy e memoria, lore con temi pronti, parole
vietate, funzioni automatiche (menzione, bandiere), moderazione con l'AI,
traduzione automatica dei canali, personaggi del server, base di
conoscenza, costruzione del server da una descrizione, stato e uso.
In più il controllo orario delle chiavi con avviso privato all'owner e il
riepilogo giornaliero dell'uso.
Funzioni coperte: SPEC §25.4, §25.7, §25.9, §25.13–§25.20, §25.23, §25.24, §25.35, §25.46, §25.58, §25.75, §25.82, §25.83, §25.96
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

import core.channel_router as router
from cogs.ai._comune import MODULO_AI, NESSUNA_MENZIONE, chiedi, completa_lingue, registra_modulo_ai, richiesta_da, taglia
from core.ai_cost_logic import GIORNI_PROVA, prova_attiva
from core.ai_router import avviso_chiavi
from core.ai_servizio import servizio_ai
from core.ai_testi_logic import ISTRUZIONI, LINGUE, TEMI, leggi_proposta_server, nome_lingua, testo_lore
from core.bot_ready import attendi_bot_pronto
from core.command_access import Livello, autocomplete_protetto
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.config import config
from core.premium import requires_module
from core.repositories.ai_repo import ai_repo
from core.repositories.output_channel_repo import output_channel_repo
from core.ui_base import BaseModal, BaseView

logger = logging.getLogger("iyokai.ai_config")

SOTTO_CONOSCENZA = ("conoscenza", "Base di conoscenza usata dall'assistente")
MAX_CONOSCENZA = 50
MAX_PAROLE_VIETATE = 50
MAX_CANALI_MODERAZIONE = 10

TESTO_CONSENSO = (
    "Accendendo l'AI, i testi delle richieste (e, per riassunti, ticket e moderazione, i messaggi "
    "degli utenti) vengono mandati ai fornitori AI configurati dal proprietario del bot. Si usano "
    "solo fornitori che dichiarano di **non addestrare** modelli con ciò che ricevono. Prima "
    "dell'invio si tolgono menzioni, ID, e-mail e inviti. L'AI propone, una persona decide: "
    "nessuna punizione parte da sola. Puoi spegnere tutto in ogni momento."
)


def _euro(millesimi: int | None) -> str:
    return f"{(millesimi or 0) / 100_000:.2f} €"


class _ConsensoView(BaseView):
    def __init__(self, autore_id: int) -> None:
        super().__init__(timeout=120)
        self.autore_id = autore_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.autore_id:
            await interaction.response.send_message("Solo chi ha avviato il comando può confermare.", ephemeral=True)
            return False
        return await super().interaction_check(interaction)

    @discord.ui.button(label="Acconsento e accendo", style=discord.ButtonStyle.success)
    async def conferma(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await ai_repo.registra_consenso(interaction.guild_id, interaction.user.id, True)
        testo = "AI accesa in questo server."
        if await _serve_la_prova(interaction.guild_id):
            prima = await ai_repo.get_config(interaction.guild_id)
            cfg = await ai_repo.avvia_prova(interaction.guild_id)
            if prima.prova_inizio is None:
                testo += f" L'AI è premium: parte una prova gratuita di {GIORNI_PROVA} giorni."
            elif not prova_attiva(cfg.prova_inizio):
                testo += " La prova gratuita è già finita: per usare l'AI serve il premium."
        await interaction.response.edit_message(content=testo, embed=None, view=None)


async def _serve_la_prova(guild_id: int) -> bool:
    """L'AI è premium e il server non l'ha sbloccata: vale la prova (una volta sola)."""
    from core.premium import guild_has_premium_access, registry

    return registry.is_module_premium(MODULO_AI) and not await guild_has_premium_access(guild_id, MODULO_AI)


class _ConoscenzaModal(BaseModal, title="Nuova voce della base di conoscenza"):
    titolo = discord.ui.TextInput(label="Titolo", max_length=100)
    testo = discord.ui.TextInput(label="Testo", style=discord.TextStyle.paragraph, max_length=1500)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if await ai_repo.conoscenza_conta(interaction.guild_id) >= MAX_CONOSCENZA:
            await interaction.response.send_message(f"Al massimo {MAX_CONOSCENZA} voci: togline una prima.", ephemeral=True)
            return
        voce = await ai_repo.conoscenza_aggiungi(
            interaction.guild_id, self.titolo.value.strip(), self.testo.value.strip(), interaction.user.id
        )
        await interaction.response.send_message(f"Voce #{voce} aggiunta.", ephemeral=True)


class _CostruisciView(BaseView):
    def __init__(self, autore_id: int, proposta) -> None:
        super().__init__(timeout=300)
        self.autore_id = autore_id
        self.proposta = proposta

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.autore_id:
            await interaction.response.send_message("Solo chi ha avviato il comando può confermare.", ephemeral=True)
            return False
        return await super().interaction_check(interaction)

    @discord.ui.button(label="Crea tutto", style=discord.ButtonStyle.success)
    async def crea(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(content="Creo ruoli e canali…", view=None)
        motivo = f"Costruzione con l'AI chiesta da {interaction.user} ({interaction.user.id})"
        creati, falliti = 0, 0
        guild = interaction.guild
        for nome in self.proposta.ruoli:
            try:
                await guild.create_role(name=nome, reason=motivo)
                creati += 1
            except discord.HTTPException:
                falliti += 1
        for nome_cat, canali in self.proposta.categorie:
            try:
                categoria = await guild.create_category(nome_cat, reason=motivo)
                creati += 1
            except discord.HTTPException:
                falliti += 1 + len(canali)
                continue
            for nome, tipo in canali:
                try:
                    if tipo == "voce":
                        await guild.create_voice_channel(nome, category=categoria, reason=motivo)
                    else:
                        await guild.create_text_channel(nome, category=categoria, reason=motivo)
                    creati += 1
                except discord.HTTPException:
                    falliti += 1
        await interaction.edit_original_response(
            content=f"Fatto: {creati} creati" + (f", {falliti} non riusciti (permessi del bot?)." if falliti else ".")
        )

    @discord.ui.button(label="Annulla", style=discord.ButtonStyle.secondary)
    async def annulla(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(content="Annullato: non ho creato niente.", embed=None, view=None)


class AiConfigCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._segnalati: frozenset[str] = frozenset()
        self._giri = 0

    async def cog_load(self) -> None:
        self._controllo_orario.start()
        await super().cog_load()

    async def cog_unload(self) -> None:
        self._controllo_orario.cancel()
        await super().cog_unload()

    # ------------------------------------------------------------ completamenti
    @autocomplete_protetto(Livello.ADMIN)
    async def _lingue(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return completa_lingue(current)

    @autocomplete_protetto(Livello.ADMIN)
    async def _personaggi(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        elenco = await ai_repo.personaggi(interaction.guild_id)
        return [
            app_commands.Choice(name=f"{p.nome}{' (installato)' if p.installato else ''}"[:100], value=p.nome)
            for p in elenco if current.lower() in p.nome.lower()
        ][:25]

    # ------------------------------------------------------------ stato e accensione
    @comando_di_gruppo("ai", nome="stato", descrizione="Stato dell'AI nel server: fornitori, scelte e uso del mese.")
    async def stato(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        servizio = servizio_ai()
        cfg = await ai_repo.get_config(interaction.guild_id)
        embed = discord.Embed(title="Intelligenza artificiale", color=discord.Color.blurple())
        fornitori = servizio.motore.fornitori
        embed.add_field(
            name="Fornitori",
            value=taglia(", ".join(f"{f.nome} ({f.fascia})" for f in fornitori), 1000) if fornitori
            else "Nessuno: l'AI non è configurata dal proprietario del bot.",
            inline=False,
        )
        embed.add_field(name="Stato", value="accesa" if cfg.attivo else "spenta")
        if cfg.prova_inizio is not None:
            fine = int(cfg.prova_inizio.timestamp()) + GIORNI_PROVA * 86400
            embed.add_field(
                name="Prova gratuita",
                value=f"fino a <t:{fine}:D>" if prova_attiva(cfg.prova_inizio) else "finita",
            )
        embed.add_field(name="Privacy", value=cfg.privacy.replace("_", " "))
        embed.add_field(name="Memoria", value=f"{cfg.conservazione_minuti} min")
        embed.add_field(
            name="Limiti",
            value=f"tetto {cfg.tetto_mensile_cent / 100:.2f} € al mese · {cfg.quota_utente_giorno} al giorno · "
            f"{cfg.quota_utente_30g} ogni 30 giorni · {cfg.quota_funzione_giorno} per funzione · "
            f"{cfg.quota_immagini_settimana} immagini a settimana",
            inline=False,
        )
        lore = testo_lore(cfg.lore_tema, cfg.lore_testo)
        embed.add_field(name="Lore", value=taglia(lore, 1000) if lore else "nessuna", inline=False)
        righe = await ai_repo.riepilogo_mese(interaction.guild_id)
        embed.add_field(
            name="Uso del mese",
            value=taglia("\n".join(
                f"{r['fornitore']}: {r['richieste']} richieste, {r['token'] or 0} token, {_euro(r['spesa'])}" for r in righe
            ) or "nessuna richiesta", 1000),
            inline=False,
        )
        if interaction.user.id == config.OWNER_ID:
            tutte = await ai_repo.riepilogo_mese(None)
            stati = [servizio.motore.stato.riepilogo(f) for f in fornitori]
            embed.add_field(
                name="Tutti i server (solo owner)",
                value=taglia("\n".join(
                    f"{r['fornitore']}: {r['richieste']} richieste, {_euro(r['spesa'])}" for r in tutte
                ) or "nessuna richiesta", 1000),
                inline=False,
            )
            embed.add_field(
                name="Quote di oggi (solo owner)",
                value=taglia("\n".join(
                    f"{f.nome}: {s['richieste_oggi']} rich., uso {s['uso']:.0%}{' · in pausa' if s['in_pausa'] else ''}"
                    for f, s in zip(fornitori, stati)
                ) or "-", 1000),
                inline=False,
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @comando_di_gruppo("ai", nome="attiva", descrizione="Accende o spegne l'AI nel server (serve il consenso).")
    @app_commands.describe(acceso="Sì per accendere, no per spegnere")
    async def attiva(self, interaction: discord.Interaction, acceso: bool) -> None:
        if not acceso:
            await ai_repo.registra_consenso(interaction.guild_id, interaction.user.id, False)
            await interaction.response.send_message("AI spenta in questo server.", ephemeral=True)
            return
        embed = discord.Embed(title="Consenso all'uso dell'AI", description=TESTO_CONSENSO, color=discord.Color.orange())
        if not servizio_ai().configurato:
            embed.add_field(name="Nota", value="Il proprietario del bot non ha ancora configurato fornitori AI.")
        await interaction.response.send_message(embed=embed, view=_ConsensoView(interaction.user.id), ephemeral=True)

    @comando_di_gruppo("ai", nome="manutenzione", descrizione="Solo proprietario: mette l'AI in manutenzione in tutti i server.")
    @app_commands.describe(acceso="Sì: l'AI si ferma ovunque (il resto del bot no); no: torna in servizio", messaggio="Cosa vedranno gli utenti")
    async def manutenzione(
        self, interaction: discord.Interaction, acceso: bool, messaggio: app_commands.Range[str, 1, 300] | None = None
    ) -> None:
        if interaction.user.id != config.OWNER_ID:
            await interaction.response.send_message("Questo comando è solo del proprietario del bot.", ephemeral=True)
            return
        await ai_repo.imposta_manutenzione(acceso, (messaggio or "").strip(), interaction.user.id)
        servizio_ai().ricarica_manutenzione()
        await interaction.response.send_message(
            "AI in manutenzione in tutti i server." if acceso else "AI di nuovo in servizio.", ephemeral=True
        )

    @comando_di_gruppo("ai", nome="canale", descrizione="Spegne o riaccende l'AI in un canale.")
    @app_commands.describe(canale="Il canale", acceso="Sì: l'AI lavora qui; no: spenta qui")
    async def canale(self, interaction: discord.Interaction, canale: discord.TextChannel, acceso: bool) -> None:
        cfg = await ai_repo.get_config(interaction.guild_id)
        spenti = [c for c in cfg.canali_spenti if c != canale.id] + ([] if acceso else [canale.id])
        await ai_repo.imposta(interaction.guild_id, canali_spenti=tuple(spenti[-100:]))
        await interaction.response.send_message(
            f"AI {'accesa' if acceso else 'spenta'} in {canale.mention}.", ephemeral=True
        )

    # ------------------------------------------------------------ limiti, privacy, lore
    @comando_di_gruppo("ai", nome="limiti", descrizione="Tetto di spesa e quote: per utente, funzione, immagini.")
    @app_commands.describe(
        tetto_euro_cent="Spesa massima al mese in centesimi (0 = solo servizi gratuiti)",
        utente_giorno="Richieste al giorno per persona (0 = senza tetto)",
        utente_30_giorni="Richieste gratuite per persona ogni 30 giorni (0 = senza tetto)",
        funzione_giorno="Richieste al giorno per ogni funzione (0 = senza tetto)",
        immagini_settimana="Immagini a settimana per persona (0 = senza tetto)",
        prezzo_pacchetto="Monete per 5 immagini in più (0 = non in vendita)",
    )
    async def limiti(
        self, interaction: discord.Interaction,
        tetto_euro_cent: app_commands.Range[int, 0, 1_000_000] | None = None,
        utente_giorno: app_commands.Range[int, 0, 10_000] | None = None,
        utente_30_giorni: app_commands.Range[int, 0, 100_000] | None = None,
        funzione_giorno: app_commands.Range[int, 0, 100_000] | None = None,
        immagini_settimana: app_commands.Range[int, 0, 1000] | None = None,
        prezzo_pacchetto: app_commands.Range[int, 0, 100_000_000] | None = None,
    ) -> None:
        campi = {
            k: v for k, v in {
                "tetto_mensile_cent": tetto_euro_cent, "quota_utente_giorno": utente_giorno,
                "quota_utente_30g": utente_30_giorni, "quota_funzione_giorno": funzione_giorno,
                "quota_immagini_settimana": immagini_settimana, "prezzo_pacchetto_immagini": prezzo_pacchetto,
            }.items() if v is not None
        }
        if not campi:
            await interaction.response.send_message("Indica almeno un valore. Lo stato attuale è in `/ai stato`.", ephemeral=True)
            return
        await ai_repo.imposta(interaction.guild_id, **campi)
        await interaction.response.send_message("Limiti salvati.", ephemeral=True)

    @comando_di_gruppo("ai", nome="privacy", descrizione="Messaggi degli utenti all'AI, memoria e lunghezza delle risposte.")
    @app_commands.describe(
        livello="completa: anche riassunti, ticket e moderazione; senza_messaggi: solo richieste dirette",
        memoria_minuti="Per quanti minuti l'AI ricorda la conversazione (0 = niente)",
        lunghezza="Lunghezza delle risposte",
    )
    @app_commands.choices(
        livello=[app_commands.Choice(name=n, value=n) for n in ("completa", "senza_messaggi")],
        lunghezza=[app_commands.Choice(name=n, value=n) for n in ("corta", "media", "lunga")],
    )
    async def privacy(
        self, interaction: discord.Interaction, livello: str | None = None,
        memoria_minuti: app_commands.Range[int, 0, 1440] | None = None, lunghezza: str | None = None,
    ) -> None:
        campi = {k: v for k, v in {"privacy": livello, "conservazione_minuti": memoria_minuti, "lunghezza": lunghezza}.items() if v is not None}
        if not campi:
            await interaction.response.send_message("Indica almeno un valore.", ephemeral=True)
            return
        await ai_repo.imposta(interaction.guild_id, **campi)
        if memoria_minuti == 0:
            servizio_ai().memoria.dimentica(interaction.guild_id)
        await interaction.response.send_message("Scelte salvate.", ephemeral=True)

    @comando_di_gruppo("ai", nome="lore", descrizione="Tono e ambientazione del server per ogni testo dell'AI.")
    @app_commands.describe(tema="Un tema pronto", testo="Le tue parole (vuoto con tema 'nessuno': toglie la lore)")
    @app_commands.choices(tema=[app_commands.Choice(name=n, value=n) for n in (*TEMI, "nessuno")])
    async def lore(
        self, interaction: discord.Interaction, tema: str, testo: app_commands.Range[str, 1, 1000] | None = None
    ) -> None:
        await ai_repo.imposta(
            interaction.guild_id, lore_tema=None if tema == "nessuno" else tema, lore_testo=(testo or "").strip() or None
        )
        lore = testo_lore(None if tema == "nessuno" else tema, testo)
        await interaction.response.send_message(
            f"Lore salvata:\n> {taglia(lore, 1500)}" if lore else "Lore tolta.", ephemeral=True
        )

    @comando_di_gruppo("ai", nome="vietate", descrizione="Parole o argomenti che l'AI deve rifiutare.")
    @app_commands.describe(azione="Cosa fare", parola="Parola o frase (per aggiungi e togli)")
    @app_commands.choices(azione=[app_commands.Choice(name=n, value=n) for n in ("aggiungi", "togli", "elenco")])
    async def vietate(
        self, interaction: discord.Interaction, azione: str, parola: app_commands.Range[str, 2, 60] | None = None
    ) -> None:
        cfg = await ai_repo.get_config(interaction.guild_id)
        parole = list(cfg.parole_vietate)
        if azione == "elenco" or parola is None:
            await interaction.response.send_message(
                taglia("Parole vietate: " + (", ".join(parole) or "nessuna"), 2000), ephemeral=True,
                allowed_mentions=NESSUNA_MENZIONE,
            )
            return
        voce = parola.strip().lower()
        if azione == "aggiungi":
            if voce not in parole:
                if len(parole) >= MAX_PAROLE_VIETATE:
                    await interaction.response.send_message(f"Al massimo {MAX_PAROLE_VIETATE} voci.", ephemeral=True)
                    return
                parole.append(voce)
        else:
            parole = [p for p in parole if p != voce]
        await ai_repo.imposta(interaction.guild_id, parole_vietate=tuple(parole))
        await interaction.response.send_message("Elenco aggiornato.", ephemeral=True)

    @comando_di_gruppo("ai", nome="funzioni", descrizione="Accende le funzioni automatiche: risposta alla menzione, bandiere.")
    @app_commands.describe(funzione="menzione: il bot risponde quando lo nomini; bandiere: traduce chi reagisce con una bandiera", acceso="Sì o no")
    @app_commands.choices(funzione=[app_commands.Choice(name=n, value=n) for n in ("menzione", "bandiere")])
    async def funzioni(self, interaction: discord.Interaction, funzione: str, acceso: bool) -> None:
        await ai_repo.imposta(interaction.guild_id, **{funzione: acceso})
        await interaction.response.send_message(f"{funzione}: {'accesa' if acceso else 'spenta'}.", ephemeral=True)

    @comando_di_gruppo("ai", nome="moderazione", descrizione="L'AI segnala allo staff i messaggi sospetti di un canale.")
    @app_commands.describe(canale="Canale da sorvegliare", acceso="Sì o no", avvisi="Dove mandare le segnalazioni (vuoto: canale dei log)")
    async def moderazione(
        self, interaction: discord.Interaction, canale: discord.TextChannel, acceso: bool,
        avvisi: discord.TextChannel | None = None,
    ) -> None:
        if avvisi is not None:
            await output_channel_repo.imposta(interaction.guild_id, router.TIPO_AI, avvisi.id)
        cfg = await ai_repo.get_config(interaction.guild_id)
        canali = [c for c in cfg.moderazione_canali if c != canale.id]
        if acceso:
            if len(canali) >= MAX_CANALI_MODERAZIONE:
                await interaction.response.send_message(f"Al massimo {MAX_CANALI_MODERAZIONE} canali.", ephemeral=True)
                return
            canali.append(canale.id)
        await ai_repo.imposta(interaction.guild_id, moderazione_canali=tuple(canali))
        await interaction.response.send_message(
            f"Sorveglianza AI {'accesa' if acceso else 'spenta'} in {canale.mention}. Le segnalazioni vanno nel "
            "canale scelto (o in quello dei log); lo staff decide.", ephemeral=True,
        )

    @comando_di_gruppo("ai", nome="traduzione", descrizione="Traduce da solo ogni messaggio di un canale in una lingua.")
    @app_commands.describe(canale="Il canale", lingua="Lingua di arrivo (vuoto: spegne)")
    @app_commands.autocomplete(lingua=_lingue)
    async def traduzione(self, interaction: discord.Interaction, canale: discord.TextChannel, lingua: app_commands.Range[str, 2, 5] | None = None) -> None:
        if lingua is not None and lingua not in LINGUE:
            await interaction.response.send_message("Lingua non riconosciuta: scegli dall'elenco.", ephemeral=True)
            return
        await ai_repo.traduzione_imposta(interaction.guild_id, canale.id, lingua)
        cog = self.bot.get_cog("AiTraduzioneCog")
        if cog is not None:
            await cog.ricarica_canali()
        await interaction.response.send_message(
            f"Traduzione automatica in {canale.mention}: {nome_lingua(lingua) if lingua else 'spenta'}.", ephemeral=True
        )

    @comando_di_gruppo("ai", nome="personaggio", descrizione="Installa, toglie o cancella un personaggio AI del server.")
    @app_commands.describe(azione="Cosa fare", nome="Il personaggio")
    @app_commands.autocomplete(nome=_personaggi)
    @app_commands.choices(azione=[app_commands.Choice(name=n, value=n) for n in ("installa", "togli", "cancella")])
    async def personaggio(self, interaction: discord.Interaction, azione: str, nome: app_commands.Range[str, 1, 40]) -> None:
        if azione == "cancella":
            ok = await ai_repo.personaggio_togli(interaction.guild_id, nome)
        else:
            ok = await ai_repo.personaggio_installa(interaction.guild_id, nome, azione == "installa")
        await interaction.response.send_message(
            f"Personaggio «{nome}»: {azione} fatto." if ok else "Personaggio non trovato.", ephemeral=True,
            allowed_mentions=NESSUNA_MENZIONE,
        )

    @comando_di_gruppo("ai", nome="costruisci", descrizione="L'AI propone ruoli e canali da una descrizione; tu confermi.")
    @app_commands.describe(descrizione="Che server vuoi? es. 'community di un gioco con tornei'")
    @requires_module(MODULO_AI)
    async def costruisci(self, interaction: discord.Interaction, descrizione: app_commands.Range[str, 10, 500]) -> None:
        await interaction.response.defer(ephemeral=True)
        risposta, locale = await chiedi(
            richiesta_da(interaction, "costruisci", "testo", descrizione, fascia="media", istruzioni=ISTRUZIONI["costruisci"])
        )
        if risposta is None:
            await interaction.followup.send(locale, ephemeral=True)
            return
        proposta = leggi_proposta_server(risposta.testo)
        if proposta is None:
            await interaction.followup.send("L'AI non ha dato una proposta leggibile: riprova con altre parole.", ephemeral=True)
            return
        righe = [f"**Ruoli:** {', '.join(proposta.ruoli) or 'nessuno'}"]
        for nome_cat, canali in proposta.categorie:
            righe.append(f"**{nome_cat}**: " + ", ".join(f"{'🔊' if t == 'voce' else '#'}{n}" for n, t in canali))
        embed = discord.Embed(title="Proposta per il server", description=taglia("\n".join(righe)), color=discord.Color.blurple())
        embed.set_footer(text=f"{len(proposta.ruoli)} ruoli, {len(proposta.categorie)} categorie, {proposta.canali_totali} canali. Niente si crea senza conferma.")
        await interaction.followup.send(embed=embed, view=_CostruisciView(interaction.user.id, proposta), ephemeral=True)

    # ------------------------------------------------------------ base di conoscenza
    @comando_di_gruppo("ai", nome="aggiungi", descrizione="Aggiunge una voce alla base di conoscenza.", sottogruppo=SOTTO_CONOSCENZA)
    async def conoscenza_aggiungi(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(_ConoscenzaModal())

    @comando_di_gruppo("ai", nome="elenco", descrizione="Le voci della base di conoscenza.", sottogruppo=SOTTO_CONOSCENZA)
    async def conoscenza_elenco(self, interaction: discord.Interaction) -> None:
        voci = await ai_repo.conoscenza_elenco(interaction.guild_id)
        testo = "\n".join(f"#{v['id']} **{v['titolo']}** — {taglia(v['testo'], 80)}" for v in voci)
        await interaction.response.send_message(
            taglia(testo or "Nessuna voce.", 2000), ephemeral=True, allowed_mentions=NESSUNA_MENZIONE
        )

    @comando_di_gruppo("ai", nome="togli", descrizione="Toglie una voce dalla base di conoscenza.", sottogruppo=SOTTO_CONOSCENZA)
    @app_commands.describe(numero="Il numero della voce (da elenco)")
    async def conoscenza_togli(self, interaction: discord.Interaction, numero: app_commands.Range[int, 1, 2_000_000_000]) -> None:
        ok = await ai_repo.conoscenza_togli(interaction.guild_id, numero)
        await interaction.response.send_message("Voce tolta." if ok else "Voce non trovata.", ephemeral=True)

    # ------------------------------------------------------------ controllo orario delle chiavi
    @tasks.loop(hours=1)
    async def _controllo_orario(self) -> None:
        servizio = servizio_ai()
        if not servizio.configurato:
            return
        try:
            esiti = await servizio.motore.controlla_chiavi()
            testo, self._segnalati = avviso_chiavi(esiti, servizio.motore.quote_in_esaurimento(), self._segnalati)
            self._giri += 1
            if self._giri % 24 == 0:
                righe = await ai_repo.riepilogo_mese(None)
                riepilogo = "\n".join(f"- {r['fornitore']}: {r['richieste']} richieste, {_euro(r['spesa'])}" for r in righe)
                testo = "\n\n".join(t for t in (testo, f"Uso dell'AI nel mese:\n{riepilogo or '- nessuna richiesta'}") if t)
            if testo:
                owner = self.bot.get_user(config.OWNER_ID) or await self.bot.fetch_user(config.OWNER_ID)
                await owner.send(taglia(testo, 2000))
        except Exception:
            logger.warning("Controllo dei fornitori AI non riuscito.", exc_info=True)

    @_controllo_orario.before_loop
    async def _prima_del_controllo(self) -> None:
        await attendi_bot_pronto(self.bot)


async def setup(bot: commands.Bot) -> None:
    registra_modulo_ai()
    await bot.add_cog(AiConfigCog(bot))
