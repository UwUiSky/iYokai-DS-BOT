"""
cogs/utility/backup.py
======================
Gruppo /admin-backup (D25, D60): coppia main e backup (main, crea, collega, promuovi),
copie datate della struttura (salva, lista, carica, elimina), stato e annullo
del caricamento (mai sopra il ruolo più alto di chi carica), esportazioni e
importazione, chat salvate (fino a 1000 messaggi) da ricaricare dopo,
modelli condivisibili con un codice e sincronia di ban e ruoli tra due server
dello stesso owner (NF-39), copia di un canale o di un ruolo, livelli di
permesso e registro.
/admin-backup ripristino modo e restore-utenti sono in cogs/utility/restore.py.
Funzioni coperte: SPEC §11.12, §11.18, §11.13, §11.15, §11.16, M 12.1, M 12.9, M 12.17, NF-39,
BKP-004 (cancella prima, D133), BKP-009, BKP-010, BKP-014, BKP-015, BKP-018, BKP-019, BKP-024…027, BKP-032…037
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
import time

import discord
from discord import app_commands
from discord.ext import commands

from core import backup_modelli_logic as modelli
from core import backup_pulizia_logic as pulizia
from core import backup_raccolta_logic as raccolta
from core import backup_struttura_logic as struttura
from core.backup_copia_logic import copia_canale, copia_ruolo
from core.backup_messages_logic import leggi_chat, ricarica_chat, webhook_chat
from core.backup_permessi_logic import (
    AZIONE_CARICA,
    AZIONE_CREA,
    LIVELLI,
    LIVELLO_PREDEFINITO,
    SETTING_LIVELLO,
    puo,
)
from core import server_sync_logic as sync
from core.database import db
from core.i18n import testo_per
from core.repositories.backup_sincronia_canali_repo import MAX_DIREZIONI_PER_SERVER, backup_sincronia_canali_repo
from core.repositories.backup_sincronia_repo import backup_sincronia_repo
from core.repositories.backup_raccolta_repo import backup_raccolta_repo
from core import piani
from core.repositories.backup_struttura_repo import MAX_COPIE_PER_SERVER, backup_struttura_repo
from core.ui_base import BaseView
from core.backup_link_logic import (
    ESITO_GIA_COLLEGATO,
    ESITO_GIA_USATO,
    ESITO_NON_AUTORIZZATO,
    ESITO_OK,
    ESITO_SCADUTO,
    ESITO_STESSO_SERVER,
    collega_backup,
    crea_codice_collegamento,
    link_invito,
    permessi_invito_creator,
    permessi_invito_main,
)

from core.command_groups import SOTTOGRUPPI, CogConGruppi, comando_di_gruppo
from core.repositories.backup_automatico_repo import backup_automatico_repo
from core.repositories.backup_mirror_repo import backup_mirror_repo
from core.repositories.backup_repo import backup_repo

logger = logging.getLogger("iyokai.backup")

_ETICHETTE_PARTI = {
    "impostazioni": "Impostazioni del server",
    "ruoli": "Ruoli e permessi",
    "canali": "Categorie e canali con i permessi",
    "emoji": "Emoji e sticker",
    "thread": "Thread e post dei forum (nomi e primo messaggio)",
    "messaggi": "Ultimi messaggi nei canali ancora vuoti",
    "ban": "Lista dei ban",
    "membri": "Nickname e ruoli dei membri presenti",
}
_LINK_MESSAGGIO = re.compile(r"(?:channels/\d+/(\d+)/)?(\d{15,21})$")


async def registra_uso(guild_id: int, user_id: int, azione: str, dettaglio: str = "") -> None:
    """BKP-019: una riga nel registro. Se il database non risponde l'azione resta fatta: solo un avviso."""
    try:
        await backup_struttura_repo.registra(guild_id, user_id, azione, dettaglio)
    except Exception:
        logger.warning("Registro del backup non scritto (%s, %s)", guild_id, azione, exc_info=True)


def tetto_di(interaction: discord.Interaction):
    """
    Il ruolo più alto di chi carica: da lì in su il caricamento non tocca ruoli
    (per l'owner del server None, nessun tetto). Senza ruoli leggibili, @everyone.
    """
    guild = interaction.guild
    if interaction.user.id == guild.owner_id:
        return None
    return getattr(interaction.user, "top_role", None) or guild.default_role


class _Interrotto:
    """Riepilogo di un caricamento che non è partito (BKP-004): conta come annullato."""

    annullato = True

    def __init__(self, messaggio: str, pulizia_fatta) -> None:
        self._messaggio, self._pulizia = messaggio, pulizia_fatta

    def testo(self) -> str:
        return ((self._pulizia.testo() + "\n") if self._pulizia else "") + self._messaggio


class _Unito:
    """Riepilogo di pulizia e caricamento insieme."""

    def __init__(self, pulizia_fatta, caricamento) -> None:
        self._pulizia, self._caricamento = pulizia_fatta, caricamento
        self.annullato = caricamento.annullato

    def testo(self) -> str:
        return self._pulizia.testo() + "\n" + self._caricamento.testo()


class ScegliPartiView(BaseView):
    """BKP-037: chi carica sceglie le parti da applicare (menu con al massimo 6 voci)."""

    def __init__(self, cog: "BackupCog", autore_id: int, dati: dict, fonte: str, guild=None) -> None:
        super().__init__(timeout=300)
        self.cog = cog
        self.autore_id = autore_id
        self.dati = dati
        self.fonte = fonte
        self.guild = guild
        # BKP-004 (D133): spente di base; le offre solo il proprietario del server.
        self.cancella_canali = False
        self.cancella_ruoli = False
        if not self._e_proprietario():
            self.remove_item(self.alterna_canali)
            self.remove_item(self.alterna_ruoli)
        presenti = struttura.parti_presenti(dati)
        self.scelte: set[str] = {p for p in presenti if p in ("ruoli", "canali")}
        menu = discord.ui.Select(
            placeholder="Cosa caricare",
            min_values=1,
            max_values=max(1, len(presenti)),
            options=[
                discord.SelectOption(label=_ETICHETTE_PARTI[p], value=p, default=p in self.scelte)
                for p in presenti
            ] or [discord.SelectOption(label="Niente da caricare", value="niente")],
        )
        menu.callback = self._scelto
        self.menu = menu
        self.add_item(menu)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.autore_id and await super().interaction_check(interaction)

    async def _scelto(self, interaction: discord.Interaction) -> None:
        self.scelte = set(self.menu.values) - {"niente"}
        await interaction.response.defer()

    def _e_proprietario(self) -> bool:
        """Letto dal server ogni volta: la proprietà può passare ad altri."""
        return self.guild is not None and self.autore_id == self.guild.owner_id

    async def _alterna(self, interaction: discord.Interaction, button: discord.ui.Button, nome: str, attributo: str) -> None:
        if not self._e_proprietario():
            setattr(self, attributo, False)
            await interaction.response.send_message(await testo_per(interaction, "backup_cancella_solo_proprietario"), ephemeral=True)
            return
        acceso = not getattr(self, attributo)
        setattr(self, attributo, acceso)
        button.label = f"Cancella prima i {nome} già presenti: {'sì' if acceso else 'no'}"
        button.style = discord.ButtonStyle.danger if acceso else discord.ButtonStyle.secondary
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Cancella prima i canali già presenti: no", style=discord.ButtonStyle.secondary, row=2)
    async def alterna_canali(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._alterna(interaction, button, "canali", "cancella_canali")

    @discord.ui.button(label="Cancella prima i ruoli già presenti: no", style=discord.ButtonStyle.secondary, row=2)
    async def alterna_ruoli(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._alterna(interaction, button, "ruoli", "cancella_ruoli")

    @discord.ui.button(label="Carica", style=discord.ButtonStyle.danger, row=1)
    async def conferma(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not self.scelte:
            await interaction.response.send_message(await testo_per(interaction, "backup_scegli_almeno_una_parte"), ephemeral=True)
            return
        if self.cancella_canali or self.cancella_ruoli:
            await self._primo_passo(interaction)
            return
        self.stop()
        testo = await self.cog.avvia_caricamento(interaction, self.dati, self.scelte, self.fonte)
        await interaction.response.edit_message(content=testo, view=None)

    async def _primo_passo(self, interaction: discord.Interaction) -> None:
        """Passo uno: il riepilogo con i numeri. Non si cancella ancora niente."""
        if not self._e_proprietario():
            await interaction.response.send_message(await testo_per(interaction, "backup_cancella_solo_proprietario"), ephemeral=True)
            return
        if (self.cancella_canali and "canali" not in self.scelte) or (self.cancella_ruoli and "ruoli" not in self.scelte):
            await interaction.response.send_message(await testo_per(interaction, "backup_cancella_serve_la_parte"), ephemeral=True)
            return
        canale = getattr(interaction, "channel", None)
        piano = pulizia.pianifica(
            self.guild, getattr(canale, "id", None), getattr(canale, "parent_id", None),
            self.cancella_canali, self.cancella_ruoli,
        )
        self.stop()
        testo = await testo_per(interaction, "backup_cancella_riepilogo", canali=len(piano.canali), ruoli=len(piano.ruoli))
        testo += "".join(f"\n• {m}: {n}" for m, n in piano.risparmiati.items())
        await interaction.response.edit_message(
            content=testo[:2000],
            view=ConfermaPuliziaView(self.cog, self.autore_id, self.dati, self.scelte, self.fonte,
                                     self.cancella_canali, self.cancella_ruoli),
        )


class ConfermaPuliziaView(BaseView):
    """BKP-004, passo due: la conferma esplicita prima di cancellare canali e ruoli."""

    def __init__(self, cog: "BackupCog", autore_id: int, dati: dict, scelte: set[str], fonte: str,
                 canali: bool, ruoli: bool) -> None:
        super().__init__(timeout=120)
        self.cog, self.autore_id, self.dati, self.scelte, self.fonte = cog, autore_id, dati, set(scelte), fonte
        self.canali, self.ruoli = canali, ruoli

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.autore_id and await super().interaction_check(interaction)

    @discord.ui.button(label="Sì, cancella e poi carica", style=discord.ButtonStyle.danger)
    async def si(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        guild = interaction.guild
        if guild is None or interaction.user.id != guild.owner_id:
            await interaction.response.send_message(await testo_per(interaction, "backup_cancella_solo_proprietario"), ephemeral=True)
            return
        self.stop()
        testo = await self.cog.avvia_caricamento(
            interaction, self.dati, self.scelte, self.fonte, cancella_canali=self.canali, cancella_ruoli=self.ruoli
        )
        await interaction.response.edit_message(content=testo, view=None)

    @discord.ui.button(label="No, annulla", style=discord.ButtonStyle.secondary)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(content=await testo_per(interaction, "backup_cancella_annullata"), view=None)


class UsaRaccoltaView(BaseView):
    """BKP-022 (D127): usa un modello della raccolta. Ruoli pericolosi e ripristino dei mancanti solo con il proprietario."""

    def __init__(self, cog: "BackupCog", interaction: discord.Interaction, dati: dict, modello_id: int) -> None:
        super().__init__(timeout=300)
        self.cog, self.autore_id, self.dati, self.modello_id = cog, interaction.user.id, dati, modello_id
        self.e_proprietario = interaction.user.id == interaction.guild.owner_id
        self.pericolosi_ok = False
        if not raccolta.ruoli_pericolosi(dati) or not self.e_proprietario:
            self.remove_item(self.conferma_pericolosi)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.autore_id and await super().interaction_check(interaction)

    @discord.ui.button(label="Confermo i ruoli con permessi pericolosi: no", style=discord.ButtonStyle.secondary, row=0)
    async def conferma_pericolosi(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.pericolosi_ok = not self.pericolosi_ok
        button.label = f"Confermo i ruoli con permessi pericolosi: {'sì' if self.pericolosi_ok else 'no'}"
        button.style = discord.ButtonStyle.danger if self.pericolosi_ok else discord.ButtonStyle.secondary
        await interaction.response.edit_message(view=self)

    async def _avvia(self, interaction: discord.Interaction, solo_mancanti: bool) -> None:
        if solo_mancanti and not self.e_proprietario:
            await interaction.response.send_message(await testo_per(interaction, "raccolta_solo_proprietario"), ephemeral=True)
            return
        self.stop()
        testo = await self.cog.avvia_caricamento(
            interaction, self.dati, {"ruoli", "canali"}, f"raccolta #{self.modello_id}",
            solo_mancanti=solo_mancanti, pericolosi_ok=self.pericolosi_ok and self.e_proprietario,
        )
        await interaction.response.edit_message(content=testo, view=None)

    @discord.ui.button(label="Crea la struttura", style=discord.ButtonStyle.danger, row=1)
    async def crea(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._avvia(interaction, False)

    @discord.ui.button(label="Solo ciò che manca (proprietario)", style=discord.ButtonStyle.primary, row=1)
    async def mancanti(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._avvia(interaction, True)


class ConfermaEliminaView(BaseView):
    """BKP-007: nessuna copia sparisce senza un clic di conferma di chi l'ha chiesto."""

    def __init__(self, autore_id: int, guild_id: int, copia: int | None) -> None:
        super().__init__(timeout=60)
        self.autore_id, self.guild_id, self.copia = autore_id, guild_id, copia

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.autore_id and await super().interaction_check(interaction)

    @discord.ui.button(label="Elimina", style=discord.ButtonStyle.danger)
    async def conferma(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        if self.copia is None:
            quante = await backup_struttura_repo.elimina_tutte(self.guild_id)
            await registra_uso(self.guild_id, self.autore_id, "elimina", f"tutte ({quante})")
            testo = await testo_per(interaction, "backup_copie_eliminate", n=quante)
        elif await backup_struttura_repo.elimina_struttura(self.guild_id, self.copia):
            await registra_uso(self.guild_id, self.autore_id, "elimina", f"#{self.copia}")
            testo = await testo_per(interaction, "backup_copia_eliminata", copia=self.copia)
        else:
            testo = await testo_per(interaction, "backup_copia_non_trovata")
        await interaction.response.edit_message(content=testo, view=None)

    @discord.ui.button(label="Annulla", style=discord.ButtonStyle.secondary)
    async def annulla(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(content=await testo_per(interaction, "backup_elimina_annullata"), view=None)


class BackupCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._lavori: set[asyncio.Task] = set()
        # Sincronie lette dal database al più ogni 5 minuti: on_member_update arriva spesso.
        self._sincronie: dict[int, tuple[float, list]] = {}
        # Ban e sban fatti dalla sincronia (con l'ora): il loro evento, entro un minuto, non torna indietro.
        self._eco: dict[tuple[int, int, str], float] = {}

    async def _puo(self, interaction: discord.Interaction, azione: str) -> bool:
        """BKP-018: controlla il livello del server e risponde se non si può."""
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                await testo_per(interaction, "guild_only_command"), ephemeral=True
            )
            return False
        livello = await db.get_guild_setting(guild.id, SETTING_LIVELLO, LIVELLO_PREDEFINITO)
        if puo(livello, azione, e_owner=interaction.user.id == guild.owner_id,
               e_admin=interaction.user.guild_permissions.administrator):
            return True
        await interaction.response.send_message(
            f"⛔ In questo server: «{LIVELLI.get(livello, LIVELLI[LIVELLO_PREDEFINITO])}» "
            "(si cambia con /founder backup permessi).",
            ephemeral=True,
        )
        return False

    async def avvia_caricamento(
        self, interaction: discord.Interaction, dati: dict, parti: set[str], fonte: str,
        solo_mancanti: bool = False, pericolosi_ok: bool | None = None,
        cancella_canali: bool = False, cancella_ruoli: bool = False,
    ) -> str:
        """
        Fa partire il caricamento di una struttura e restituisce il testo per chi l'ha chiesto.
        BKP-004 (D133): con `cancella_*` prima si cancella (solo il proprietario, ricontrollato qui e
        dentro la pulizia); se la cancellazione si ferma, il caricamento non parte.
        """
        guild = interaction.guild
        tetto = tetto_di(interaction)
        cancella = cancella_canali or cancella_ruoli
        autore = interaction.user.id
        if cancella and autore != guild.owner_id:
            return await testo_per(interaction, "backup_cancella_solo_proprietario")
        canale = getattr(interaction, "channel", None)
        canale_id, genitore_id = getattr(canale, "id", None), getattr(canale, "parent_id", None)
        da_cancellare = pulizia.pianifica(guild, canale_id, genitore_id, cancella_canali, cancella_ruoli).totale if cancella else 0

        async def lavoro(avanza):
            testa = None
            if cancella:
                try:
                    testa = await pulizia.esegui(
                        guild, autore, canale_id, genitore_id, cancella_canali, cancella_ruoli, avanza=avanza
                    )
                except pulizia.PuliziaNegata:
                    return _Interrotto("⛔ Solo il proprietario del server può cancellare canali e ruoli.", None)
                if testa.interrotta:
                    return _Interrotto("⏹️ La cancellazione si è fermata: **il caricamento non è partito**. Ciò che era già fatto resta.", testa)

            async def avanza_dopo(passo: str, fatti: int, totale: int) -> bool:
                return await avanza(passo, fatti + da_cancellare, totale + da_cancellare)

            caricatore = struttura.Caricatore(
                guild, dati, parti, avanza=avanza_dopo if cancella else avanza, scarica=struttura.scarica_immagine,
                tetto=tetto, solo_mancanti=solo_mancanti, pericolosi_ok=pericolosi_ok,
            )
            riepilogo = await caricatore.esegui()
            return _Unito(testa, riepilogo) if testa else riepilogo

        dettaglio = ", ".join(sorted(parti))
        if cancella:
            cosa = " e ".join(n for n, v in (("canali", cancella_canali), ("ruoli", cancella_ruoli)) if v)
            dettaglio += f" (prima cancella: {cosa})"
        return await self.avvia_lavoro(
            interaction, fonte, struttura.conta_passi(dati, parti) + da_cancellare, dettaglio, lavoro
        )

    async def avvia_lavoro(self, interaction: discord.Interaction, fonte: str, totale: int, dettaglio: str, lavoro) -> str:
        """
        Un caricamento in sottofondo, uno per server: `lavoro(avanza)` restituisce un
        riepilogo con `annullato` e `testo()`. Stato e annullo da /admin-backup stato e annulla.
        """
        guild = interaction.guild
        caricamento_id = await backup_struttura_repo.avvia_caricamento(guild.id, interaction.user.id, fonte, totale)
        if caricamento_id is None:
            return "⏳ C'è già un caricamento in corso: guarda /admin-backup stato o fermalo con /admin-backup annulla."

        async def avanza(passo: str, fatti: int, totale: int) -> bool:
            return await backup_struttura_repo.aggiorna_caricamento(caricamento_id, passo, fatti, totale)

        await registra_uso(guild.id, interaction.user.id, "carica", f"{fonte}: {dettaglio}")
        compito = asyncio.create_task(self._esegui(lavoro, avanza, caricamento_id, interaction.channel))
        self._lavori.add(compito)
        compito.add_done_callback(self._lavori.discard)
        return "▶️ Caricamento avviato. Avanzamento: /admin-backup stato · per fermarlo: /admin-backup annulla."

    async def _esegui(self, lavoro, avanza, caricamento_id: int, canale) -> None:
        """Il riepilogo va nel canale: il lavoro può durare più di 15 minuti."""
        stato = "fallito"
        testo = "❌ Caricamento interrotto da un errore: ciò che era già fatto resta."
        try:
            riepilogo = await lavoro(avanza)
            stato = "annullato" if riepilogo.annullato else "finito"
            testo = "📦 **Caricamento del backup finito.**\n" + riepilogo.testo()
        except Exception:
            logger.exception("Caricamento del backup %s fallito", caricamento_id)
        finally:
            await backup_struttura_repo.chiudi_caricamento(caricamento_id, stato)
        if canale is not None:
            try:
                await canale.send(testo[:2000])
            except discord.HTTPException:
                pass

    @comando_di_gruppo(
        "admin-backup",
        nome="main",
        descrizione="Registra questo server come 'main' per il Backup System.",
    )
    async def define_main(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                await testo_per(interaction, "guild_only_command"), ephemeral=True
            )
            return

        await backup_repo.define_main(guild.id)
        await registra_uso(guild.id, interaction.user.id, "main")
        await interaction.response.send_message(
            await testo_per(interaction, "backup_questo_server_ora_registrato_come"),
            ephemeral=True,
        )

    async def _link_modello(self, guild: discord.Guild) -> str | None:
        """Link del modello di server (riusa quello esistente). None se Discord rifiuta."""
        try:
            modelli = await guild.templates()
            if modelli:
                await modelli[0].sync()
                return modelli[0].url
            modello = await guild.create_template(
                name=guild.name[:100], description="Modello per il server di backup (iYokai)"
            )
            return modello.url
        except discord.HTTPException:
            return None

    @comando_di_gruppo(
        "admin-backup",
        nome="crea",
        descrizione="Prepara il backup: codice di collegamento e link per il nuovo server.",
    )
    @app_commands.describe(modello="Crea anche un link modello di server (ruoli e canali già pronti)")
    async def define_backup(self, interaction: discord.Interaction, modello: bool = False) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                await testo_per(interaction, "guild_only_command"), ephemeral=True
            )
            return
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                await testo_per(interaction, "backup_serve_il_permesso_amministratore"), ephemeral=True
            )
            return

        coppia = await backup_repo.get_pair(guild.id)
        if coppia is None:
            await interaction.response.send_message(
                await testo_per(interaction, "backup_devi_prima_registrare_questo_server"), ephemeral=True
            )
            return

        if await backup_repo.has_active_job(guild.id):
            await interaction.response.send_message(
                await testo_per(interaction, "backup_gia_una_copia_in_coda"),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        codice, scadenza = await crea_codice_collegamento(
            backup_repo, guild.id, creato_da=interaction.user.id
        )
        await registra_uso(guild.id, interaction.user.id, "crea")
        creator = getattr(self.bot, "backup_creator_client", None)
        link_creator = (
            link_invito(creator.user.id, permessi_invito_creator())
            if creator is not None and creator.user is not None
            else None
        )
        link_main = link_invito(self.bot.user.id, permessi_invito_main())
        url_modello = await self._link_modello(guild) if modello else None

        passi = [
            "1. Crea un server nuovo (anche da un modello).",
            f"2. Invita **iYokai** con [questo link]({link_main})."
            + (f" Invita anche **iYokai Creator** con [questo link]({link_creator})." if link_creator else " (Il Creator non è attivo: avvisa l'owner del bot.)"),
            f"3. Nel server nuovo lancia `/admin-backup collega` con il codice `{codice}`.",
        ]
        if modello:
            passi.insert(
                1,
                f"   Modello: {url_modello}" if url_modello else "   Modello non creato: Discord ha rifiutato.",
            )
        embed = discord.Embed(
            title=await testo_per(interaction, "backup_collegamento_del_backup"),
            description="\n".join(passi)[:4000],
            color=discord.Color.blurple(),
        )
        embed.set_footer(text=await testo_per(interaction, "backup_il_codice_vale_fino_utc", scadenza=scadenza))
        await interaction.followup.send(embed=embed, ephemeral=True)

    @comando_di_gruppo(
        "admin-backup",
        nome="collega",
        descrizione="Collega QUESTO server come backup, con il codice ricevuto dal server principale.",
    )
    @app_commands.describe(codice="Codice dato da /admin-backup crea nel server principale")
    async def collega(
        self, interaction: discord.Interaction, codice: app_commands.Range[str, 4, 24]
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                await testo_per(interaction, "guild_only_command"), ephemeral=True
            )
            return
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                await testo_per(interaction, "backup_serve_il_permesso_amministratore"), ephemeral=True
            )
            return

        creator = getattr(self.bot, "backup_creator_client", None)
        if creator is None or creator.get_guild(guild.id) is None:
            await interaction.response.send_message(
                await testo_per(interaction, "backup_iyokai_creator_non_in_questo"),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        async def e_admin_del_main(main_guild_id: int) -> bool:
            main = self.bot.get_guild(main_guild_id)
            membro = main.get_member(interaction.user.id) if main is not None else None
            return membro is not None and (
                membro.guild_permissions.administrator or main.owner_id == membro.id
            )

        esito = await collega_backup(
            backup_repo, codice, guild.id,
            utente_id=interaction.user.id, puo_collegare=e_admin_del_main,
        )
        if esito.esito == ESITO_OK:
            await registra_uso(guild.id, interaction.user.id, "collega", f"job #{esito.job_id}")
            await interaction.followup.send(
                await testo_per(interaction, "backup_server_collegato_come_backup_job", job_id=esito.job_id),
                ephemeral=True,
            )
            return
        messaggi = {
            ESITO_SCADUTO: "⌛ Il codice è scaduto: creane uno nuovo con /admin-backup crea.",
            ESITO_GIA_USATO: "⚠️ Il codice è già stato usato: creane uno nuovo con /admin-backup crea.",
            ESITO_GIA_COLLEGATO: (
                "⚠️ Collegamento non possibile: o questo server fa già parte di un'altra coppia, "
                "o il server principale ha già un backup o una copia in corso."
            ),
            ESITO_NON_AUTORIZZATO: (
                "⛔ Il codice lo può usare solo chi lo ha creato, e deve essere ancora "
                "amministratore del server principale."
            ),
            ESITO_STESSO_SERVER: "⚠️ Il server principale non può essere il proprio backup.",
        }
        await interaction.followup.send(
            messaggi.get(esito.esito, "❌ Codice non valido."), ephemeral=True
        )

    @comando_di_gruppo(
        "admin-backup",
        nome="promuovi",
        descrizione="Promuove QUESTO server (finora backup) a nuovo main, se il main originale è perso.",
    )
    async def promuovi_backup(self, interaction: discord.Interaction) -> None:
        """
        SPEC.md §11.13 — il backup promosso diventa main senza backup:
        un admin ne crea uno nuovo con /admin-backup crea (un bot non può
        creare server, D8). La coppia storica resta per /admin-backup ripristino utenti.

        Va lanciato DENTRO al server che finora era il backup — non
        serve altro ID: lo troviamo risalendo da backup_guild_id a
        chi era il suo main tramite get_pair_by_backup_guild_id.
        """
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                await testo_per(interaction, "guild_only_command"), ephemeral=True
            )
            return

        if not await self._puo(interaction, AZIONE_CARICA):
            return  # 11.13: promuovere pesa quanto caricare una copia

        coppia = await backup_repo.get_pair_by_backup_guild_id(guild.id)
        if coppia is None:
            await interaction.response.send_message(
                await testo_per(interaction, "backup_questo_server_non_risulta_registrato"),
                ephemeral=True,
            )
            return

        await backup_repo.promote_backup_to_main(
            old_main_guild_id=coppia.main_guild_id, new_main_guild_id=guild.id
        )
        # Il mirror del vecchio main scriveva in questo server: ora non serve più.
        await backup_mirror_repo.delete_for_main_guild(coppia.main_guild_id)
        await registra_uso(guild.id, interaction.user.id, "promuovi", str(coppia.main_guild_id))

        await interaction.response.send_message(
            await testo_per(interaction, "backup_questo_server_stato_promosso_main", main_guild_id=coppia.main_guild_id),
            ephemeral=True,
        )

    # ------------------------------------------------------------
    # Copie datate della struttura (M 12.17)
    # ------------------------------------------------------------
    @comando_di_gruppo("admin-backup", nome="salva", descrizione="Salva una copia datata della struttura di questo server.")
    @app_commands.describe(
        nome="Nome della copia",
        ban="Salva anche la lista dei ban",
        membri="Salva anche nickname e ruoli dei membri",
        messaggi="Salva anche gli ultimi N messaggi di ogni canale di testo (0-100)",
        thread="Salva anche i thread pubblici e i post dei forum (nome e primo messaggio)",
    )
    async def salva(
        self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, 50],
        ban: bool = False, membri: bool = False, messaggi: app_commands.Range[int, 0, 100] = 0,
        thread: bool = False,
    ) -> None:
        if not await self._puo(interaction, AZIONE_CREA):
            return
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        dati = struttura.leggi_struttura(guild)
        if ban:
            try:
                dati["ban"] = await struttura.leggi_ban(guild)
            except discord.HTTPException:
                await interaction.followup.send(await testo_per(interaction, "backup_mi_serve_il_permesso_banna"), ephemeral=True)
                return
        if membri:
            dati["membri"] = struttura.leggi_membri(guild)
        if messaggi:
            dati["messaggi"] = await self._ultimi_messaggi(guild, messaggi)
        if thread:
            dati["thread"] = await struttura.leggi_thread(guild)
        if len(struttura.in_json(dati)) > struttura.MAX_FILE_BYTE:
            await interaction.followup.send(await testo_per(interaction, "backup_la_copia_supera_mib_salvala"), ephemeral=True)
            return
        copia_id = await backup_struttura_repo.salva_struttura(guild.id, nome, interaction.user.id, dati)
        if copia_id is None:
            await interaction.followup.send(
                await testo_per(interaction, "backup_ci_sono_gia_copie_eliminane", v1=await piani.limite_server_sicuro(interaction.guild.id, "backup_copie")), ephemeral=True
            )
            return
        await registra_uso(guild.id, interaction.user.id, "salva", f"#{copia_id} {nome}")
        await interaction.followup.send(
            f"✅ Copia `#{copia_id}` salvata: {len(dati['ruoli'])} ruoli, {len(dati['canali'])} canali"
            + (f", {len(dati['ban'])} ban" if ban else "")
            + (f", {len(dati['membri'])} membri" if membri else "")
            + (f", {sum(len(m) for m in dati['messaggi'].values())} messaggi" if messaggi else "")
            + (f", {len(dati['thread'])} thread" if thread else "") + ".",
            ephemeral=True,
        )

    async def _ultimi_messaggi(self, guild: discord.Guild, quanti: int) -> dict[str, list]:
        """M 12.17: gli ultimi messaggi di ogni canale di testo leggibile, per nome (un canale alla volta)."""
        risultato: dict[str, list] = {}
        for canale in guild.text_channels:
            if canale.name == struttura.NOME_CANALE_OFFUSCATO or canale.name in risultato:
                continue
            try:
                righe = await leggi_chat(canale, quanti)
            except discord.HTTPException:
                continue  # canale che il bot non legge
            if righe:
                risultato[canale.name] = righe
        return risultato

    @comando_di_gruppo("admin-backup", nome="lista", descrizione="Le copie salvate, con la data; con un numero, cosa contiene una copia.")
    @app_commands.describe(copia="Numero di una copia: ne mostra il contenuto senza caricarla")
    async def lista(self, interaction: discord.Interaction, copia: app_commands.Range[int, 1] | None = None) -> None:
        if not await self._puo(interaction, AZIONE_CREA):
            return
        if copia is not None:
            await self._info_copia(interaction, copia)
            return
        copie = await backup_struttura_repo.lista_strutture(interaction.guild.id)
        if not copie:
            await interaction.response.send_message(await testo_per(interaction, "backup_nessuna_copia_salvata_usa_backup"), ephemeral=True)
            return
        righe = [
            f"`#{c.id}` {'💬' if c.chat else '⏱️' if c.automatica else '🏗️'} **{discord.utils.escape_markdown(c.nome)}** · "
            f"{discord.utils.format_dt(c.creato_il, 'f')}"
            + (f" · modello `{c.codice_modello}`" if c.codice_modello else "")
            for c in copie
        ]
        embed = discord.Embed(title=await testo_per(interaction, "backup_copie_salvate"), description="\n".join(righe)[:4000], color=discord.Color.blurple())
        embed.set_footer(text=await testo_per(interaction, "backup_al_massimo_copie_per_server", v1=await piani.limite_server_sicuro(interaction.guild.id, "backup_copie")))
        await interaction.response.send_message(embed=embed, ephemeral=True)


    async def _info_copia(self, interaction: discord.Interaction, copia: int) -> None:
        """BKP-006: nome, data e conteggi della copia, senza caricarla."""
        trovata = await backup_struttura_repo.leggi_con_data(interaction.guild.id, copia)
        if trovata is None:
            await interaction.response.send_message(await testo_per(interaction, "backup_copia_non_trovata"), ephemeral=True)
            return
        nome, creato_il, dati = trovata
        conteggi = struttura.riassunto(dati)
        etichette = {
            "ruoli": "ruoli", "categorie": "categorie", "canali": "canali", "emoji": "emoji", "sticker": "sticker",
            "ban": "ban", "membri": "membri", "messaggi": "messaggi", "thread": "thread",
        }
        righe = [f"**{etichette[k]}**: {v}" for k, v in conteggi.items()] or [await testo_per(interaction, "backup_copia_vuota")]
        embed = discord.Embed(
            title=f"#{copia} · {nome}"[:256], description="\n".join(righe)[:4000], color=discord.Color.blurple(),
        )
        embed.add_field(name=await testo_per(interaction, "backup_info_creata"), value=discord.utils.format_dt(creato_il, "f"))
        embed.add_field(
            name=await testo_per(interaction, "backup_info_tipo"),
            value=await testo_per(interaction, "backup_info_tipo_chat" if dati.get("tipo") == "chat" else "backup_info_tipo_struttura"),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @comando_di_gruppo("admin-backup", nome="carica", descrizione="Ricarica in questo server una copia salvata, scegliendo le parti.")
    @app_commands.describe(
        copia="Numero della copia (da /admin-backup lista)",
        ultima_automatica="Dopo un attacco: la copia automatica più recente, solo la struttura (solo il proprietario)",
    )
    async def carica(
        self, interaction: discord.Interaction, copia: app_commands.Range[int, 1] | None = None, ultima_automatica: bool = False
    ) -> None:
        if not await self._puo(interaction, AZIONE_CARICA):
            return
        if ultima_automatica == (copia is not None):
            await interaction.response.send_message(await testo_per(interaction, "backup_carica_scegli"), ephemeral=True)
            return
        fonte = f"copia #{copia}"
        if ultima_automatica:  # SIC-016
            if interaction.user.id != interaction.guild.owner_id:
                await interaction.response.send_message(await testo_per(interaction, "backup_ultima_solo_proprietario"), ephemeral=True)
                return
            trovata = await backup_struttura_repo.ultima_automatica(interaction.guild.id)
            if trovata is None:
                await interaction.response.send_message(await testo_per(interaction, "backup_nessuna_automatica"), ephemeral=True)
                return
            copia, quando, dati = trovata
            dati = struttura.solo_struttura(dati)
            fonte = f"copia automatica #{copia} del {quando:%d/%m %H:%M}"
        else:
            dati = await backup_struttura_repo.leggi_struttura(interaction.guild.id, copia)
        if dati is None:
            await interaction.response.send_message(await testo_per(interaction, "backup_copia_non_trovata_guarda_backup"), ephemeral=True)
            return
        if dati.get("tipo") == "chat":
            await interaction.response.send_message(await testo_per(interaction, "backup_questa_una_chat_salvata_usa"), ephemeral=True)
            return
        await interaction.response.send_message(
            await testo_per(interaction, "backup_copia_scegli_cosa_caricare_cio", copia=copia),
            view=ScegliPartiView(self, interaction.user.id, dati, fonte, guild=interaction.guild),
            ephemeral=True,
        )

    @comando_di_gruppo("founder", nome="automatico", descrizione="Copie automatiche della struttura a intervalli.", sottogruppo=SOTTOGRUPPI["founder backup"])
    @app_commands.describe(
        ore="Ogni quante ore (3-168); vuoto con «spegni» per fermarle",
        copie="Quante copie automatiche tenere (1-8): la più vecchia si sovrascrive",
        spegni="Ferma le copie automatiche",
    )
    async def automatico(
        self, interaction: discord.Interaction, ore: app_commands.Range[int, 3, 168] | None = None,
        copie: app_commands.Range[int, 1, 8] = 3, spegni: bool = False,
    ) -> None:
        """BKP-008."""
        if not await self._puo(interaction, AZIONE_CREA):
            return
        guild = interaction.guild
        if spegni:
            fatto = await backup_automatico_repo.togli(guild.id)
            if fatto:
                await registra_uso(guild.id, interaction.user.id, "automatico", "spento")
            await interaction.response.send_message(
                await testo_per(interaction, "backup_automatico_spento" if fatto else "backup_automatico_non_attivo"), ephemeral=True
            )
            return
        if ore is None:
            attuale = await backup_automatico_repo.leggi(guild.id)
            testo = (
                await testo_per(interaction, "backup_automatico_attivo", ore=attuale.ore, copie=attuale.copie)
                if attuale else await testo_per(interaction, "backup_automatico_non_attivo")
            )
            await interaction.response.send_message(testo, ephemeral=True)
            return
        await backup_automatico_repo.imposta(guild.id, ore, copie, interaction.user.id)
        await registra_uso(guild.id, interaction.user.id, "automatico", f"{ore} ore, {copie} copie")
        await interaction.response.send_message(
            await testo_per(interaction, "backup_automatico_attivo", ore=ore, copie=copie), ephemeral=True
        )

    @comando_di_gruppo("admin-backup", nome="elimina", descrizione="Elimina una copia salvata, o tutte (con conferma).")
    @app_commands.describe(copia="Numero della copia (da /admin-backup lista)", tutte="Elimina tutte le copie del server")
    async def elimina(
        self, interaction: discord.Interaction, copia: app_commands.Range[int, 1] | None = None, tutte: bool = False,
    ) -> None:
        """BKP-007: sempre con un bottone di conferma."""
        if not await self._puo(interaction, AZIONE_CREA):
            return
        if tutte == (copia is not None):
            await interaction.response.send_message(await testo_per(interaction, "backup_elimina_scegli"), ephemeral=True)
            return
        if copia is not None and await backup_struttura_repo.leggi_struttura(interaction.guild.id, copia) is None:
            await interaction.response.send_message(await testo_per(interaction, "backup_copia_non_trovata"), ephemeral=True)
            return
        await interaction.response.send_message(
            await testo_per(interaction, "backup_elimina_conferma_tutte" if tutte else "backup_elimina_conferma", copia=copia),
            view=ConfermaEliminaView(interaction.user.id, interaction.guild.id, copia),
            ephemeral=True,
        )

    @comando_di_gruppo("admin-backup", nome="stato", descrizione="Avanzamento dell'ultimo caricamento in questo server.")
    async def stato(self, interaction: discord.Interaction) -> None:
        if not await self._puo(interaction, AZIONE_CREA):
            return
        c = await backup_struttura_repo.ultimo_caricamento(interaction.guild.id)
        righe = []
        if c is not None:
            nomi = {"in_corso": "⏳ in corso", "finito": "✅ finito", "annullato": "⏹️ annullato", "fallito": "❌ fallito"}
            percentuale = f" ({c.fatti * 100 // c.totale}%)" if c.totale else ""
            righe.append(
                f"Caricamento da {c.fonte}, avviato {discord.utils.format_dt(c.creato_il, 'R')}: "
                f"**{nomi.get(c.stato, c.stato)}**. Passo: {c.passo or '—'} · {c.fatti}/{c.totale}{percentuale}"
                + (" · annullo chiesto" if c.annulla and c.stato == "in_corso" else "")
            )
        # 11.17: ora ed esito dell'ultimo aggiornamento automatico del server di backup.
        coppia = await backup_repo.get_pair(interaction.guild.id)
        if coppia is None or coppia.backup_guild_id is None:
            coppia = await backup_repo.get_pair_by_backup_guild_id(interaction.guild.id)
        if coppia is not None and coppia.backup_guild_id is not None:
            if coppia.ultimo_allineamento is None:
                righe.append("Aggiornamento automatico del backup: non ancora eseguito (ogni 6 ore).")
            else:
                righe.append(
                    "Aggiornamento automatico del backup: "
                    f"{discord.utils.format_dt(coppia.ultimo_allineamento, 'R')} · "
                    f"{coppia.esito_allineamento or '—'}"
                )
        if not righe:
            await interaction.response.send_message(await testo_per(interaction, "backup_nessun_caricamento_in_questo_server"), ephemeral=True)
            return
        await interaction.response.send_message("\n".join(righe)[:1900], ephemeral=True)

    @comando_di_gruppo("admin-backup", nome="annulla", descrizione="Ferma il caricamento in corso (ciò che è già fatto resta).")
    async def annulla(self, interaction: discord.Interaction) -> None:
        if not await self._puo(interaction, AZIONE_CARICA):
            return
        if not await backup_struttura_repo.chiedi_annullo(interaction.guild.id):
            await interaction.response.send_message(await testo_per(interaction, "backup_nessun_caricamento_in_corso"), ephemeral=True)
            return
        await registra_uso(interaction.guild.id, interaction.user.id, "annulla")
        await interaction.response.send_message(await testo_per(interaction, "backup_annullo_chiesto_si_ferma_al"), ephemeral=True)

    # ------------------------------------------------------------
    # Modelli (NF-39)
    # ------------------------------------------------------------
    async def _leggi_modello(self, testo: str) -> tuple[str, dict, str] | None:
        """BKP-020: (nome, dati, descrizione) da un modello pronto, un codice nostro o un modello di Discord."""
        pronto = modelli.trova_pronto(testo)
        if pronto is not None:
            return pronto[1]["titolo"], pronto[1]["dati"], pronto[1]["descrizione"]
        nostro = await backup_struttura_repo.leggi_modello(testo.strip())
        if nostro is not None:
            return nostro[0], nostro[1], ""
        codice = modelli.codice_discord(testo)
        if codice is None:
            return None
        try:
            esterno = await self.bot.fetch_template(codice)
        except discord.HTTPException:
            return None
        letto = modelli.da_modello_discord(esterno)
        return (letto[0], letto[1], (esterno.description or "")[:200]) if letto is not None else None

    @comando_di_gruppo("admin-backup", nome="modello", descrizione="Modelli: pronti, tuoi o di Discord. Elenco, scheda, uso e condivisione.")
    @app_commands.describe(
        azione="Cosa fare",
        copia="Per «pubblica» e «ritira»: numero della copia (da /admin-backup lista)",
        codice="Per «usa» e «scheda»: nome di un modello pronto, codice o link discord.new",
    )
    @app_commands.choices(
        azione=[
            app_commands.Choice(name="Elenco dei modelli", value="elenco"),
            app_commands.Choice(name="Scheda di un modello", value="scheda"),
            app_commands.Choice(name="Pubblica una copia come modello", value="pubblica"),
            app_commands.Choice(name="Usa un modello in questo server", value="usa"),
            app_commands.Choice(name="Ritira il codice di un modello", value="ritira"),
        ]
    )
    async def modello(
        self, interaction: discord.Interaction, azione: app_commands.Choice[str],
        copia: app_commands.Range[int, 1] | None = None,
        codice: app_commands.Range[str, 2, 100] | None = None,
    ) -> None:
        if not await self._puo(interaction, AZIONE_CARICA if azione.value == "usa" else AZIONE_CREA):
            return
        guild = interaction.guild
        if azione.value == "elenco":
            righe = [f"🧩 **{m['titolo']}** (`{k}`): {m['descrizione']}" for k, m in modelli.MODELLI_PRONTI.items()]
            miei = [c for c in await backup_struttura_repo.lista_strutture(guild.id) if c.codice_modello]
            righe += [f"📎 `#{c.id}` {discord.utils.escape_markdown(c.nome)}: codice `{c.codice_modello}`" for c in miei]
            embed = discord.Embed(
                title=await testo_per(interaction, "backup_modelli_titolo"), description="\n".join(righe)[:4000],
                color=discord.Color.blurple(),
            )
            embed.set_footer(text=await testo_per(interaction, "backup_modelli_piede"))
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        if azione.value == "scheda":
            await interaction.response.defer(ephemeral=True)
            letto = await self._leggi_modello(codice) if codice else None
            if letto is None:
                await interaction.followup.send(await testo_per(interaction, "backup_modello_non_trovato_controlla_il"), ephemeral=True)
                return
            nome, dati, descrizione = letto
            conteggi = struttura.riassunto(struttura.senza_dati_personali(dati))
            embed = discord.Embed(
                title=nome[:256], description=(discord.utils.escape_markdown(descrizione) or "—")[:1000],
                color=discord.Color.blurple(),
            )
            embed.add_field(
                name=await testo_per(interaction, "backup_modello_contiene"),
                value=", ".join(f"{k}: {v}" for k, v in conteggi.items()) or "—", inline=False,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        if azione.value == "usa":
            if codice:
                await interaction.response.defer(ephemeral=True)
            letto = await self._leggi_modello(codice) if codice else None
            if letto is None:
                invia = interaction.followup.send if codice else interaction.response.send_message
                await invia(await testo_per(interaction, "backup_modello_non_trovato_controlla_il"), ephemeral=True)
                return
            nome, dati, _desc = letto
            await interaction.followup.send(
                await testo_per(interaction, "backup_modello_senza_ban_membri_permessi", v1=discord.utils.escape_markdown(nome)),
                view=ScegliPartiView(self, interaction.user.id, struttura.senza_dati_personali(dati), f"modello {codice[:60]}", guild=interaction.guild),
                ephemeral=True,
            )
            return
        if copia is None:
            await interaction.response.send_message(await testo_per(interaction, "backup_scrivi_il_numero_della_copia"), ephemeral=True)
            return
        if azione.value == "pubblica":
            nuovo = await backup_struttura_repo.pubblica_modello(guild.id, copia)
            testo = (
                f"🧩 Modello pronto: codice `{nuovo}`. Chi lo ha può caricarlo con /admin-backup modello "
                "(ban, membri e permessi dei singoli non passano)." if nuovo else "Copia non trovata (le chat salvate non diventano modelli)."
            )
        else:
            nuovo = await backup_struttura_repo.ritira_modello(guild.id, copia)
            testo = "Codice ritirato: il modello non si può più usare." if nuovo else "Quella copia non è un modello."
        if nuovo:
            await registra_uso(guild.id, interaction.user.id, f"modello {azione.value}", f"#{copia}")
        await interaction.response.send_message(testo, ephemeral=True)

    # ------------------------------------------------------------
    # Raccolta pubblica dei modelli (BKP-022/023, D127)
    # ------------------------------------------------------------
    @comando_di_gruppo("admin-backup", nome="raccolta", descrizione="Raccolta pubblica di modelli: elenco, voto, uso e proposta.")
    @app_commands.describe(
        azione="Cosa fare", modello="Numero del modello nella raccolta", copia="Per «proponi»: numero della tua copia",
        nome="Per «proponi»: nome del modello", descrizione="Per «proponi»: a cosa serve", cerca="Per «elenco»: testo da cercare",
    )
    @app_commands.choices(
        azione=[
            app_commands.Choice(name="Elenco dei modelli approvati", value="elenco"),
            app_commands.Choice(name="Vota un modello", value="vota"),
            app_commands.Choice(name="Usa un modello", value="usa"),
            app_commands.Choice(name="Proponi una tua copia", value="proponi"),
            app_commands.Choice(name="Le mie proposte", value="mie"),
        ]
    )
    async def raccolta_cmd(
        self, interaction: discord.Interaction, azione: app_commands.Choice[str],
        modello: app_commands.Range[int, 1, 2**31 - 1] | None = None, copia: app_commands.Range[int, 1] | None = None,
        nome: app_commands.Range[str, 3, 60] | None = None, descrizione: app_commands.Range[str, 0, 300] = "",
        cerca: app_commands.Range[str, 0, 40] = "",
    ) -> None:
        if not await self._puo(interaction, AZIONE_CARICA if azione.value in ("usa", "elenco", "vota") else AZIONE_CREA):
            return
        guild = interaction.guild
        if azione.value == "elenco":
            voci = await backup_raccolta_repo.elenco_pubblico(lingua=None, ricerca=raccolta.ricerca_pulita(cerca), limite=20)
            righe = [
                await testo_per(
                    interaction, "raccolta_riga", id=m.id, nome=discord.utils.escape_markdown(m.nome), voti=m.voti,
                    ruoli=m.ruoli, canali=m.canali, lingua=m.lingua,
                ) for m in voci
            ]
            testo = "\n".join(righe)[:3900] if righe else await testo_per(interaction, "raccolta_elenco_vuoto")
            embed = discord.Embed(title=await testo_per(interaction, "raccolta_titolo"), description=testo, color=discord.Color.blurple())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        if azione.value == "mie":
            mie = await backup_raccolta_repo.del_server(guild.id)
            righe = [await testo_per(interaction, "raccolta_mia_riga", id=m.id, nome=discord.utils.escape_markdown(m.nome),
                                     stato=await testo_per(interaction, f"raccolta_stato_{m.stato}")) for m in mie]
            await interaction.response.send_message(
                "\n".join(righe)[:1900] if righe else await testo_per(interaction, "raccolta_nessuna_mia"), ephemeral=True
            )
            return
        if azione.value == "proponi":
            if copia is None or nome is None:
                await interaction.response.send_message(await testo_per(interaction, "raccolta_serve_copia"), ephemeral=True)
                return
            trovata = await backup_struttura_repo.leggi_struttura(guild.id, copia)
            pulita, errori = raccolta.prepara_struttura(trovata) if trovata is not None else (None, ["copia non trovata"])
            titolo = raccolta.nome_modello(nome)
            if pulita is None or titolo is None:
                await interaction.response.send_message(
                    await testo_per(interaction, "raccolta_proposta_non_valida", errori="; ".join(errori[:3]) or nome), ephemeral=True
                )
                return
            lingua = interaction.locale.value if getattr(interaction, "locale", None) else "it"
            nuovo = await backup_raccolta_repo.proponi(
                guild.id, interaction.user.id, titolo, raccolta.descrizione_modello(descrizione),
                raccolta.lingua_valida(lingua) or "it", pulita,
            )
            if nuovo is None:
                await interaction.response.send_message(await testo_per(interaction, "raccolta_proposta_troppe"), ephemeral=True)
                return
            await registra_uso(guild.id, interaction.user.id, "raccolta proponi", f"#{copia} -> {nuovo}")
            await interaction.response.send_message(await testo_per(interaction, "raccolta_proposta_ok", id=nuovo), ephemeral=True)
            return
        if modello is None:
            await interaction.response.send_message(await testo_per(interaction, "raccolta_non_trovato"), ephemeral=True)
            return
        if azione.value == "vota":
            esito = await backup_raccolta_repo.vota(modello, interaction.user.id)
            chiave = {"nuovo": "raccolta_voto_nuovo", "gia": "raccolta_voto_gia"}.get(esito, "raccolta_non_trovato")
            await interaction.response.send_message(await testo_per(interaction, chiave), ephemeral=True)
            return
        trovato = await backup_raccolta_repo.leggi_pubblico(modello)
        if trovato is None:
            await interaction.response.send_message(await testo_per(interaction, "raccolta_non_trovato"), ephemeral=True)
            return
        scheda, dati = trovato
        manca = raccolta.mancanti(guild, dati)
        pericolosi = raccolta.ruoli_pericolosi(dati)
        testo = await testo_per(
            interaction, "raccolta_usa", nome=discord.utils.escape_markdown(scheda.nome), mancano=manca.totale(),
            pericolosi=discord.utils.escape_markdown(", ".join(pericolosi)) or "-",
        )
        await interaction.response.send_message(testo[:1900], view=UsaRaccoltaView(self, interaction, dati, modello), ephemeral=True)

    # ------------------------------------------------------------
    # Sincronia di ban e ruoli (NF-39)
    # ------------------------------------------------------------
    @comando_di_gruppo("founder", nome="sincronia", descrizione="Tieni uguali ban e ruoli con un altro tuo server.", sottogruppo=SOTTOGRUPPI["founder backup"])
    @app_commands.describe(
        azione="Cosa fare",
        server="ID dell'altro server (per «attiva» e «disattiva»)",
        ban="Copia ban e sban",
        ruoli="Copia i ruoli dati e tolti (per nome)",
    )
    @app_commands.choices(
        azione=[
            app_commands.Choice(name="Attiva o aggiorna", value="attiva"),
            app_commands.Choice(name="Disattiva", value="disattiva"),
            app_commands.Choice(name="Elenco", value="elenco"),
        ]
    )
    async def sincronia(
        self, interaction: discord.Interaction, azione: app_commands.Choice[str],
        server: app_commands.Range[str, 15, 21] | None = None, ban: bool = True, ruoli: bool = True,
    ) -> None:
        guild = interaction.guild
        if guild is None or interaction.user.id != guild.owner_id:
            await interaction.response.send_message(await testo_per(interaction, "backup_la_sincronia_la_gestisce_solo"), ephemeral=True)
            return
        if azione.value == "elenco":
            elenco = await backup_sincronia_repo.sincronie_di(guild.id)
            righe = [
                f"`{s.altro}` {discord.utils.escape_markdown(getattr(self.bot.get_guild(s.altro), 'name', '?'))}"
                f" · ban {'sì' if s.ban else 'no'} · ruoli {'sì' if s.ruoli else 'no'}"
                for s in elenco
            ]
            await interaction.response.send_message("\n".join(righe) or "Nessuna sincronia.", ephemeral=True)
            return
        if server is None or not server.isdigit() or int(server) == guild.id:
            await interaction.response.send_message(await testo_per(interaction, "backup_scrivi_id_dell_altro_server"), ephemeral=True)
            return
        altro_id = int(server)
        if azione.value == "disattiva":
            fatto = await backup_sincronia_repo.disattiva(guild.id, altro_id)
            testo = "Sincronia disattivata." if fatto else "Nessuna sincronia con quel server."
        else:
            altro = self.bot.get_guild(altro_id)
            if altro is None:
                await interaction.response.send_message(await testo_per(interaction, "backup_non_sono_in_quel_server"), ephemeral=True)
                return
            if not sync.stesso_proprietario(interaction.user.id, guild.owner_id, altro.owner_id):
                await interaction.response.send_message(await testo_per(interaction, "backup_devi_essere_owner_di_entrambi"), ephemeral=True)
                return
            fatto = await backup_sincronia_repo.attiva(guild.id, altro_id, ban, ruoli, interaction.user.id)
            testo = (
                f"🔗 Sincronia con **{discord.utils.escape_markdown(altro.name)}**: ban {'sì' if ban else 'no'}, "
                f"ruoli {'sì' if ruoli else 'no'}. Vale da adesso in poi, nei due sensi."
                if fatto else f"⚠️ Uno dei due server ha già {sync.MAX_SINCRONIE_PER_SERVER} sincronie."
            )
        if fatto:
            self._sincronie.pop(guild.id, None)
            self._sincronie.pop(altro_id, None)
            await registra_uso(guild.id, interaction.user.id, f"sincronia {azione.value}", server)
        await interaction.response.send_message(testo, ephemeral=True)

    @comando_di_gruppo("founder", nome="sincronia-canali", descrizione="Copia i messaggi tra due canali tuoi, in una o in due direzioni.", sottogruppo=SOTTOGRUPPI["founder backup"])
    @app_commands.describe(
        azione="Cosa fare",
        canale="Il canale di QUESTO server",
        altro_canale="ID dell'altro canale (anche di un altro tuo server)",
        direzione="Verso dove vanno i messaggi (per «attiva»)",
    )
    @app_commands.choices(
        azione=[
            app_commands.Choice(name="Attiva", value="attiva"),
            app_commands.Choice(name="Disattiva", value="disattiva"),
            app_commands.Choice(name="Elenco", value="elenco"),
        ],
        direzione=[
            app_commands.Choice(name="Da questo canale all'altro", value="verso_altro"),
            app_commands.Choice(name="Dall'altro canale a questo", value="verso_qui"),
            app_commands.Choice(name="In tutte e due le direzioni", value="due_sensi"),
        ],
    )
    async def sincronia_canali(
        self, interaction: discord.Interaction, azione: app_commands.Choice[str],
        canale: discord.TextChannel | None = None, altro_canale: app_commands.Range[str, 15, 21] | None = None,
        direzione: app_commands.Choice[str] | None = None,
    ) -> None:
        """BKP-028: solo l'owner di entrambi i server; i messaggi di bot e webhook non si copiano (niente cicli)."""
        guild = interaction.guild
        if guild is None or interaction.user.id != guild.owner_id:
            await interaction.response.send_message(await testo_per(interaction, "backup_la_sincronia_la_gestisce_solo"), ephemeral=True)
            return
        if azione.value == "elenco":
            elenco = await backup_sincronia_canali_repo.elenco(guild.id)
            righe = [f"<#{d.canale_da}> → <#{d.canale_a}>" for d in elenco]
            await interaction.response.send_message(
                "\n".join(righe) or await testo_per(interaction, "backup_sync_canali_nessuna"), ephemeral=True
            )
            return
        altro = self.bot.get_channel(int(altro_canale)) if altro_canale and altro_canale.isdigit() else None
        if canale is None or not isinstance(altro, discord.TextChannel) or altro.id == canale.id:
            await interaction.response.send_message(await testo_per(interaction, "backup_sync_canali_scegli"), ephemeral=True)
            return
        if not sync.stesso_proprietario(interaction.user.id, guild.owner_id, altro.guild.owner_id):
            await interaction.response.send_message(await testo_per(interaction, "backup_devi_essere_owner_di_entrambi"), ephemeral=True)
            return
        if azione.value == "disattiva":
            tolte = await backup_sincronia_canali_repo.togli_coppia(guild.id, canale.id, altro.id)
            if tolte:
                await registra_uso(guild.id, interaction.user.id, "sincronia canali", f"togli {canale.id} {altro.id}")
            await interaction.response.send_message(
                await testo_per(interaction, "backup_sync_canali_tolta" if tolte else "backup_sync_canali_nessuna"), ephemeral=True
            )
            return
        scelta = direzione.value if direzione else "due_sensi"
        coppie = []
        if scelta in ("verso_altro", "due_sensi"):
            coppie.append((canale, altro))
        if scelta in ("verso_qui", "due_sensi"):
            coppie.append((altro, canale))
        await interaction.response.defer(ephemeral=True)
        for origine, arrivo in coppie:
            try:
                hook = await webhook_chat(arrivo)
            except discord.HTTPException:
                hook = None
            if hook is None or not hook.url:
                await interaction.followup.send(await testo_per(interaction, "backup_sync_canali_webhook", v1=arrivo.mention), ephemeral=True)
                return
            ok = await backup_sincronia_canali_repo.attiva(
                origine.id, origine.guild.id, arrivo.id, arrivo.guild.id, hook.url, interaction.user.id
            )
            if not ok:
                await interaction.followup.send(
                    await testo_per(interaction, "backup_sync_canali_troppe", v1=MAX_DIREZIONI_PER_SERVER), ephemeral=True
                )
                return
        await registra_uso(guild.id, interaction.user.id, "sincronia canali", f"{scelta} {canale.id} {altro.id}")
        await interaction.followup.send(
            await testo_per(interaction, "backup_sync_canali_attiva", v1=canale.mention, v2=altro.name), ephemeral=True
        )

    async def _sincronie_di(self, guild_id: int) -> list:
        letto = self._sincronie.get(guild_id)
        if letto is None or time.monotonic() - letto[0] > 300:
            letto = (time.monotonic(), await backup_sincronia_repo.sincronie_di(guild_id))
            self._sincronie[guild_id] = letto
        return letto[1]

    async def _altri_server(self, guild: discord.Guild, campo: str):
        """Gli altri server in sincronia; la proprietà si ricontrolla ora (un server può essere stato ceduto)."""
        for s in await self._sincronie_di(guild.id):
            altro = self.bot.get_guild(s.altro) if getattr(s, campo) else None
            if altro is not None and altro.owner_id == guild.owner_id:
                yield altro

    async def _ban_sincronizzato(self, guild: discord.Guild, user, banna: bool) -> None:
        tipo = "ban" if banna else "sban"
        ora = time.monotonic()
        self._eco = {k: t for k, t in self._eco.items() if ora - t < 60}
        if self._eco.pop((guild.id, user.id, tipo), None) is not None:
            return
        async for altro in self._altri_server(guild, "ban"):
            self._eco[(altro.id, user.id, tipo)] = ora
            try:
                if banna:
                    await altro.ban(user, reason=sync.motivo(guild.name, None), delete_message_seconds=0)
                else:
                    await altro.unban(user, reason=sync.motivo(guild.name, None))
            except discord.HTTPException:
                self._eco.pop((altro.id, user.id, tipo), None)  # nessun evento tornerà
                logger.warning("Sincronia %s di %s da %s a %s non riuscita", tipo, user.id, guild.id, altro.id)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user) -> None:
        await self._ban_sincronizzato(guild, user, banna=True)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user) -> None:
        await self._ban_sincronizzato(guild, user, banna=False)

    @commands.Cog.listener()
    async def on_member_update(self, prima: discord.Member, dopo: discord.Member) -> None:
        """Ruoli dati o tolti: lo stesso nell'altro server. Se è già così non si chiama Discord (niente eco)."""
        aggiunti, tolti = sync.differenza_ruoli(
            {r.name for r in prima.roles}, {r.name for r in dopo.roles}
        )
        if not aggiunti and not tolti:
            return
        permessi_sorgente = {r.name: r.permissions.value for r in dopo.roles}
        async for altro in self._altri_server(dopo.guild, "ruoli"):
            membro = altro.get_member(dopo.id)
            if membro is None or altro.me is None:
                continue
            presenti = set(membro.roles)
            da_dare = [
                r for r in sync.ruoli_applicabili(aggiunti, altro.roles, altro.me.top_role, permessi_sorgente)
                if r not in presenti
            ]
            da_togliere = [r for r in sync.ruoli_applicabili(tolti, altro.roles, altro.me.top_role) if r in presenti]
            try:
                if da_dare:
                    await membro.add_roles(*da_dare, reason=sync.motivo(dopo.guild.name, None))
                if da_togliere:
                    await membro.remove_roles(*da_togliere, reason=sync.motivo(dopo.guild.name, None))
            except discord.HTTPException:
                logger.warning("Sincronia ruoli di %s verso %s non riuscita", dopo.id, altro.id)

    # ------------------------------------------------------------
    # Copia di un canale o di un ruolo (BKP-024, BKP-025)
    # ------------------------------------------------------------
    @comando_di_gruppo("admin-backup", nome="canale", descrizione="Copia un canale con i permessi; una categoria con i suoi canali.", sottogruppo=SOTTOGRUPPI["admin-backup copia"])
    @app_commands.describe(canale="Canale o categoria da copiare", nome="Nome della copia (se vuoto, lo stesso)")
    async def copia_canale_cmd(
        self, interaction: discord.Interaction, canale: discord.abc.GuildChannel,
        nome: app_commands.Range[str, 1, 100] | None = None,
    ) -> None:
        if not await self._puo(interaction, AZIONE_CREA):
            return
        await interaction.response.defer(ephemeral=True)
        try:
            esito = await copia_canale(interaction.guild, canale, nome)
        except discord.HTTPException:
            await interaction.followup.send(await testo_per(interaction, "backup_discord_ha_rifiutato_la_copia"), ephemeral=True)
            return
        if esito.errore:
            await interaction.followup.send(f"⚠️ {esito.errore}", ephemeral=True)
            return
        await registra_uso(interaction.guild.id, interaction.user.id, "copia-canale", canale.name)
        await interaction.followup.send(
            f"✅ Copia creata: {esito.nuovo.mention}. Canali copiati: {esito.copiati}"
            + (f" · saltati: {esito.saltati}" if esito.saltati else "")
            + (f" · non riusciti: {esito.falliti}" if esito.falliti else ""),
            ephemeral=True,
        )

    @comando_di_gruppo("admin-backup", nome="ruolo", descrizione="Copia un ruolo con i permessi e, a scelta, i permessi nei canali.", sottogruppo=SOTTOGRUPPI["admin-backup copia"])
    @app_commands.describe(
        ruolo="Ruolo da copiare", nome="Nome della copia (se vuoto, lo stesso)",
        permessi_canali="Copia anche i permessi del ruolo nei canali",
    )
    async def copia_ruolo_cmd(
        self, interaction: discord.Interaction, ruolo: discord.Role,
        nome: app_commands.Range[str, 1, 100] | None = None, permessi_canali: bool = False,
    ) -> None:
        if not await self._puo(interaction, AZIONE_CREA):
            return
        await interaction.response.defer(ephemeral=True)
        try:
            esito = await copia_ruolo(interaction.guild, ruolo, nome, permessi_canali)
        except discord.HTTPException:
            await interaction.followup.send(await testo_per(interaction, "backup_discord_ha_rifiutato_la_copia"), ephemeral=True)
            return
        if esito.errore:
            await interaction.followup.send(f"⚠️ {esito.errore}", ephemeral=True)
            return
        await registra_uso(interaction.guild.id, interaction.user.id, "copia-ruolo", ruolo.name)
        await interaction.followup.send(
            f"✅ Copia creata: {esito.nuovo.mention}"
            + (f" · permessi nei canali: {esito.copiati - 1}" if permessi_canali else "")
            + (" · alcuni permessi tolti (non li ho)" if esito.saltati else "")
            + (f" · non riusciti: {esito.falliti}" if esito.falliti else ""),
            ephemeral=True,
        )

    # ------------------------------------------------------------
    # Chat salvate (BKP-026, BKP-027)
    # ------------------------------------------------------------
    @comando_di_gruppo("admin-backup", nome="salva", descrizione="Salva gli ultimi messaggi di un canale (fino a 1000) per ricaricarli dopo.", sottogruppo=SOTTOGRUPPI["admin-backup chat"])
    @app_commands.describe(
        canale="Canale da salvare (se vuoto, questo)", quanti="Quanti messaggi (1-1000)", nome="Nome della copia",
    )
    async def chat_salva(
        self, interaction: discord.Interaction, canale: discord.TextChannel | None = None,
        quanti: app_commands.Range[int, 1, 1000] = 100, nome: app_commands.Range[str, 1, 50] | None = None,
    ) -> None:
        if not await self._puo(interaction, AZIONE_CREA):
            return
        canale = canale or interaction.channel
        if not isinstance(canale, discord.TextChannel):
            await interaction.response.send_message(await testo_per(interaction, "embedbuilder_scegli_un_canale_di_testo"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            messaggi = await leggi_chat(canale, quanti)
        except discord.HTTPException:
            await interaction.followup.send(await testo_per(interaction, "backup_non_riesco_leggere_quel_canale"), ephemeral=True)
            return
        dati = {"versione": struttura.VERSIONE, "tipo": "chat", "canale": canale.name, "messaggi": messaggi}
        if len(struttura.in_json(dati)) > struttura.MAX_FILE_BYTE:
            await interaction.followup.send(await testo_per(interaction, "backup_troppi_dati_salva_meno_messaggi"), ephemeral=True)
            return
        copia_id = await backup_struttura_repo.salva_struttura(
            interaction.guild.id, nome or f"chat #{canale.name}"[:50], interaction.user.id, dati
        )
        if copia_id is None:
            await interaction.followup.send(
                await testo_per(interaction, "backup_ci_sono_gia_copie_eliminane", v1=await piani.limite_server_sicuro(interaction.guild.id, "backup_copie")), ephemeral=True
            )
            return
        await registra_uso(interaction.guild.id, interaction.user.id, "chat-salva", f"#{copia_id} {canale.name}")
        await interaction.followup.send(
            await testo_per(interaction, "backup_chat_salvata_come_copia_messaggi", copia_id=copia_id, v2=len(messaggi)),
            ephemeral=True,
        )

    @comando_di_gruppo("admin-backup", nome="carica", descrizione="Ricarica una chat salvata in un canale, anche diverso.", sottogruppo=SOTTOGRUPPI["admin-backup chat"])
    @app_commands.describe(copia="Numero della chat salvata (da /admin-backup lista)", canale="Canale dove ricaricarla (se vuoto, questo)")
    async def chat_carica(
        self, interaction: discord.Interaction, copia: app_commands.Range[int, 1],
        canale: discord.TextChannel | None = None,
    ) -> None:
        if not await self._puo(interaction, AZIONE_CARICA):
            return
        canale = canale or interaction.channel
        dati = await backup_struttura_repo.leggi_struttura(interaction.guild.id, copia)
        if dati is None or dati.get("tipo") != "chat":
            await interaction.response.send_message(await testo_per(interaction, "backup_chat_salvata_non_trovata_guarda"), ephemeral=True)
            return
        if not isinstance(canale, discord.TextChannel):
            await interaction.response.send_message(await testo_per(interaction, "embedbuilder_scegli_un_canale_di_testo"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            webhook = await webhook_chat(canale)
        except discord.HTTPException:
            webhook = None
        if webhook is None:
            await interaction.followup.send(
                await testo_per(interaction, "backup_non_posso_usare_un_webhook"),
                ephemeral=True,
            )
            return
        messaggi = dati.get("messaggi", [])

        async def lavoro(avanza):
            return await ricarica_chat(messaggi, webhook, canale, avanza, struttura.scarica_file)

        testo = await self.avvia_lavoro(interaction, f"chat #{copia}", len(messaggi), canale.name, lavoro)
        await interaction.followup.send(testo, ephemeral=True)

    # ------------------------------------------------------------
    # Esportazioni e importazione (BKP-032…037)
    # ------------------------------------------------------------
    @comando_di_gruppo("admin-backup", nome="esporta", descrizione="Esporta struttura, canali, ruoli, ban o reazioni in un file.")
    @app_commands.describe(
        cosa="Cosa esportare",
        formato="JSON o CSV (la struttura intera è sempre JSON)",
        canale="Per «un canale»: il canale",
        ruolo="Per «un ruolo»: il ruolo",
        messaggio="Per «reazioni»: link o ID del messaggio",
    )
    @app_commands.choices(
        cosa=[
            app_commands.Choice(name="Struttura del server", value="struttura"),
            app_commands.Choice(name="Tutti i canali", value="canali"),
            app_commands.Choice(name="Tutti i ruoli", value="ruoli"),
            app_commands.Choice(name="Un canale con i permessi", value="canale"),
            app_commands.Choice(name="Un ruolo con i permessi", value="ruolo"),
            app_commands.Choice(name="Ban con i motivi", value="ban"),
            app_commands.Choice(name="Reazioni a un messaggio", value="reazioni"),
        ],
        formato=[app_commands.Choice(name="JSON", value="json"), app_commands.Choice(name="CSV", value="csv")],
    )
    async def esporta(
        self, interaction: discord.Interaction, cosa: app_commands.Choice[str],
        formato: app_commands.Choice[str] | None = None,
        canale: discord.abc.GuildChannel | None = None, ruolo: discord.Role | None = None,
        messaggio: app_commands.Range[str, 1, 120] | None = None,
    ) -> None:
        if not await self._puo(interaction, AZIONE_CREA):
            return
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        tipo = cosa.value
        try:
            righe = await self._righe_da_esportare(interaction, tipo, canale, ruolo, messaggio)
        except discord.HTTPException:
            await interaction.followup.send(await testo_per(interaction, "backup_discord_ha_rifiutato_la_lettura"), ephemeral=True)
            return
        if isinstance(righe, str):
            await interaction.followup.send(righe, ephemeral=True)
            return
        tipo_csv = "canali" if tipo == "canale" else "ruoli" if tipo == "ruolo" else tipo
        contenuto, estensione = struttura.esporta(tipo_csv, formato.value if formato else "json", righe)
        if len(contenuto) > struttura.MAX_FILE_BYTE:
            await interaction.followup.send(await testo_per(interaction, "backup_il_file_supera_mib"), ephemeral=True)
            return
        await registra_uso(guild.id, interaction.user.id, "esporta", tipo)
        await interaction.followup.send(
            await testo_per(interaction, "backup_esportazione", name=cosa.name),
            file=discord.File(io.BytesIO(contenuto), filename=f"{tipo}-{guild.id}.{estensione}"),
            ephemeral=True,
        )

    async def _righe_da_esportare(self, interaction, tipo, canale, ruolo, messaggio):
        """Le righe da esportare, o il testo dell'errore da mostrare."""
        guild = interaction.guild
        if tipo == "struttura":
            return struttura.leggi_struttura(guild)
        if tipo == "canali":
            return struttura.leggi_struttura(guild)["canali"]
        if tipo == "ruoli":
            return struttura.leggi_struttura(guild)["ruoli"]
        if tipo == "canale":
            if canale is None or canale.type not in struttura._TIPI:
                return "Scegli un canale di testo, vocale, annunci, palco o forum nell'opzione «canale»."
            return [struttura.leggi_canale(canale)]
        if tipo == "ruolo":
            if ruolo is None:
                return "Scegli il ruolo nell'opzione «ruolo»."
            return [struttura.leggi_ruolo(ruolo)]
        if tipo == "ban":
            return await struttura.leggi_ban(guild)
        trovato = _LINK_MESSAGGIO.search((messaggio or "").strip())
        if trovato is None:
            return "Scrivi nell'opzione «messaggio» il link o l'ID del messaggio."
        dove = guild.get_channel(int(trovato.group(1))) if trovato.group(1) else interaction.channel
        if dove is None or not hasattr(dove, "fetch_message"):
            return "Canale del messaggio non trovato in questo server."
        try:
            msg = await dove.fetch_message(int(trovato.group(2)))
        except discord.NotFound:
            return "Messaggio non trovato."
        return await struttura.leggi_reazioni(msg)

    @comando_di_gruppo("admin-backup", nome="importa", descrizione="Importa la struttura da un file JSON, scegliendo cosa applicare.")
    @app_commands.describe(file="File JSON esportato con /admin-backup esporta (al massimo 10 MiB)")
    async def importa(self, interaction: discord.Interaction, file: discord.Attachment) -> None:
        if not await self._puo(interaction, AZIONE_CARICA):
            return
        if file.size > struttura.MAX_FILE_BYTE:
            await interaction.response.send_message(await testo_per(interaction, "backup_il_file_supera_mib"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            contenuto = await file.read()
        except discord.HTTPException:
            await interaction.followup.send(await testo_per(interaction, "backup_non_riesco_leggere_il_file"), ephemeral=True)
            return
        dati, errori = struttura.leggi_json(contenuto)
        if dati is None:
            await interaction.followup.send(
                "❌ File non valido, il server non è stato toccato:\n" + "\n".join(f"• {e}" for e in errori)[:1800],
                ephemeral=True,
            )
            return
        # L'esportazione non contiene i membri: un file che li ha viene da fuori e
        # darebbe ruoli a ID scelti da chi l'ha scritto.
        dati.pop("membri", None)
        await interaction.followup.send(
            await testo_per(interaction, "backup_file_valido_scegli_cosa_caricare"),
            view=ScegliPartiView(self, interaction.user.id, dati, f"file {file.filename[:60]}", guild=interaction.guild),
            ephemeral=True,
        )

    # ------------------------------------------------------------
    # Permessi e registro (BKP-018, BKP-019)
    # ------------------------------------------------------------
    @comando_di_gruppo("founder", nome="permessi", descrizione="Chi può creare e chi può caricare i backup (solo l'owner).", sottogruppo=SOTTOGRUPPI["founder backup"])
    @app_commands.describe(livello="Chi può fare cosa")
    @app_commands.choices(livello=[app_commands.Choice(name=v, value=k) for k, v in LIVELLI.items()])
    async def permessi(self, interaction: discord.Interaction, livello: app_commands.Choice[str]) -> None:
        guild = interaction.guild
        if guild is None or interaction.user.id != guild.owner_id:
            await interaction.response.send_message(await testo_per(interaction, "backup_solo_owner_del_server_sceglie"), ephemeral=True)
            return
        await db.set_guild_setting(guild.id, SETTING_LIVELLO, livello.value)
        await registra_uso(guild.id, interaction.user.id, "permessi", livello.value)
        await interaction.response.send_message(await testo_per(interaction, "backup_backup", name=livello.name), ephemeral=True)

    @comando_di_gruppo("admin-backup", nome="registro", descrizione="Chi ha usato backup, modelli e sincronie (ultimi 20, 365 giorni).")
    async def registro(self, interaction: discord.Interaction) -> None:
        if not await self._puo(interaction, AZIONE_CREA):
            return
        righe = await backup_struttura_repo.leggi_registro(interaction.guild.id)
        if not righe:
            await interaction.response.send_message(await testo_per(interaction, "backup_registro_vuoto"), ephemeral=True)
            return
        testo = "\n".join(
            f"{discord.utils.format_dt(r['creato_il'], 'd')} <@{r['user_id']}> **{r['azione']}** "
            f"{discord.utils.escape_markdown(r['dettaglio'])}"
            for r in righe
        )
        embed = discord.Embed(title=await testo_per(interaction, "backup_registro_del_backup"), description=testo[:4000], color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BackupCog(bot))
