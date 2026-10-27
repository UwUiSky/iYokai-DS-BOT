"""
cogs/utility/backup.py
======================
Gruppo /backup (D25): coppia main e backup (main, crea, collega, promuovi),
copie datate della struttura (salva, lista, carica, elimina), stato e annullo
del caricamento (mai sopra il ruolo più alto di chi carica), esportazioni e
importazione, chat salvate (fino a 1000 messaggi) da ricaricare dopo,
modelli condivisibili con un codice e sincronia di ban e ruoli tra due server
dello stesso owner (NF-39), copia di un canale o di un ruolo, livelli di
permesso e registro.
/backup restore-modo e restore-utenti sono in cogs/utility/restore.py.
Funzioni coperte: SPEC §11.12, §11.13, §11.15, §11.16, M 12.1, M 12.9, M 12.17, NF-39,
BKP-009, BKP-010, BKP-014, BKP-015, BKP-018, BKP-019, BKP-024…027, BKP-032…037
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
from core.repositories.backup_sincronia_repo import backup_sincronia_repo
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

from core.command_groups import CogConGruppi, comando_di_gruppo
from core.repositories.backup_mirror_repo import backup_mirror_repo
from core.repositories.backup_repo import backup_repo

logger = logging.getLogger("iyokai.backup")

_ETICHETTE_PARTI = {
    "impostazioni": "Impostazioni del server",
    "ruoli": "Ruoli e permessi",
    "canali": "Categorie e canali con i permessi",
    "emoji": "Emoji e sticker",
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


class ScegliPartiView(BaseView):
    """BKP-037: chi carica sceglie le parti da applicare (menu con al massimo 6 voci)."""

    def __init__(self, cog: "BackupCog", autore_id: int, dati: dict, fonte: str) -> None:
        super().__init__(timeout=300)
        self.cog = cog
        self.autore_id = autore_id
        self.dati = dati
        self.fonte = fonte
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

    @discord.ui.button(label="Carica", style=discord.ButtonStyle.danger, row=1)
    async def conferma(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not self.scelte:
            await interaction.response.send_message("Scegli almeno una parte.", ephemeral=True)
            return
        self.stop()
        testo = await self.cog.avvia_caricamento(interaction, self.dati, self.scelte, self.fonte)
        await interaction.response.edit_message(content=testo, view=None)


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
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return False
        livello = await db.get_guild_setting(guild.id, SETTING_LIVELLO, LIVELLO_PREDEFINITO)
        if puo(livello, azione, e_owner=interaction.user.id == guild.owner_id,
               e_admin=interaction.user.guild_permissions.administrator):
            return True
        await interaction.response.send_message(
            f"⛔ In questo server: «{LIVELLI.get(livello, LIVELLI[LIVELLO_PREDEFINITO])}» "
            "(si cambia con /backup permessi).",
            ephemeral=True,
        )
        return False

    async def avvia_caricamento(
        self, interaction: discord.Interaction, dati: dict, parti: set[str], fonte: str
    ) -> str:
        """Fa partire il caricamento di una struttura e restituisce il testo per chi l'ha chiesto."""
        guild = interaction.guild
        tetto = tetto_di(interaction)

        async def lavoro(avanza):
            caricatore = struttura.Caricatore(
                guild, dati, parti, avanza=avanza, scarica=struttura.scarica_immagine, tetto=tetto
            )
            return await caricatore.esegui()

        return await self.avvia_lavoro(
            interaction, fonte, struttura.conta_passi(dati, parti), ", ".join(sorted(parti)), lavoro
        )

    async def avvia_lavoro(self, interaction: discord.Interaction, fonte: str, totale: int, dettaglio: str, lavoro) -> str:
        """
        Un caricamento in sottofondo, uno per server: `lavoro(avanza)` restituisce un
        riepilogo con `annullato` e `testo()`. Stato e annullo da /backup stato e annulla.
        """
        guild = interaction.guild
        caricamento_id = await backup_struttura_repo.avvia_caricamento(guild.id, interaction.user.id, fonte, totale)
        if caricamento_id is None:
            return "⏳ C'è già un caricamento in corso: guarda /backup stato o fermalo con /backup annulla."

        async def avanza(passo: str, fatti: int, totale: int) -> bool:
            return await backup_struttura_repo.aggiorna_caricamento(caricamento_id, passo, fatti, totale)

        await registra_uso(guild.id, interaction.user.id, "carica", f"{fonte}: {dettaglio}")
        compito = asyncio.create_task(self._esegui(lavoro, avanza, caricamento_id, interaction.channel))
        self._lavori.add(compito)
        compito.add_done_callback(self._lavori.discard)
        return "▶️ Caricamento avviato. Avanzamento: /backup stato · per fermarlo: /backup annulla."

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
        "backup",
        nome="main",
        descrizione="Registra questo server come 'main' per il Backup System.",
    )
    async def define_main(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        await backup_repo.define_main(guild.id)
        await registra_uso(guild.id, interaction.user.id, "main")
        await interaction.response.send_message(
            "✅ Questo server è ora registrato come 'main' per il Backup System. "
            "Usa /backup crea per collegare un server di backup.",
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
        "backup",
        nome="crea",
        descrizione="Prepara il backup: codice di collegamento e link per il nuovo server.",
    )
    @app_commands.describe(modello="Crea anche un link modello di server (ruoli e canali già pronti)")
    async def define_backup(self, interaction: discord.Interaction, modello: bool = False) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "Serve il permesso Amministratore.", ephemeral=True
            )
            return

        coppia = await backup_repo.get_pair(guild.id)
        if coppia is None:
            await interaction.response.send_message(
                "Devi prima registrare questo server con /backup main.", ephemeral=True
            )
            return

        if await backup_repo.has_active_job(guild.id):
            await interaction.response.send_message(
                "⏳ C'è già una copia in coda o in corso per questo server: "
                "attendi che finisca prima di prepararne un'altra.",
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
            f"3. Nel server nuovo lancia `/backup collega` con il codice `{codice}`.",
        ]
        if modello:
            passi.insert(
                1,
                f"   Modello: {url_modello}" if url_modello else "   Modello non creato: Discord ha rifiutato.",
            )
        embed = discord.Embed(
            title="📦 Collegamento del backup",
            description="\n".join(passi)[:4000],
            color=discord.Color.blurple(),
        )
        embed.set_footer(text=f"Il codice vale fino a {scadenza:%d/%m %H:%M} UTC e si usa una volta sola.")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @comando_di_gruppo(
        "backup",
        nome="collega",
        descrizione="Collega QUESTO server come backup, con il codice ricevuto dal server principale.",
    )
    @app_commands.describe(codice="Codice dato da /backup crea nel server principale")
    async def collega(
        self, interaction: discord.Interaction, codice: app_commands.Range[str, 4, 24]
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "Serve il permesso Amministratore.", ephemeral=True
            )
            return

        creator = getattr(self.bot, "backup_creator_client", None)
        if creator is None or creator.get_guild(guild.id) is None:
            await interaction.response.send_message(
                "⚠️ **iYokai Creator** non è in questo server: invitalo (il link è in "
                "`/backup crea`) e rilancia il comando.",
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
                f"✅ Server collegato come backup (job `#{esito.job_id}`). Il Creator copia "
                "la struttura e gli ultimi 50 messaggi di ogni canale: riceverai un DM quando ha finito, poi lo tiene aggiornato.",
                ephemeral=True,
            )
            return
        messaggi = {
            ESITO_SCADUTO: "⌛ Il codice è scaduto: creane uno nuovo con /backup crea.",
            ESITO_GIA_USATO: "⚠️ Il codice è già stato usato: creane uno nuovo con /backup crea.",
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
        "backup",
        nome="promuovi",
        descrizione="Promuove QUESTO server (finora backup) a nuovo main, se il main originale è perso.",
    )
    async def promuovi_backup(self, interaction: discord.Interaction) -> None:
        """
        SPEC.md §11.13 — il backup promosso diventa main senza backup:
        un admin ne crea uno nuovo con /backup crea (un bot non può
        creare server, D8). La coppia storica resta per /backup restore-utenti.

        Va lanciato DENTRO al server che finora era il backup — non
        serve altro ID: lo troviamo risalendo da backup_guild_id a
        chi era il suo main tramite get_pair_by_backup_guild_id.
        """
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        if not await self._puo(interaction, AZIONE_CARICA):
            return  # 11.13: promuovere pesa quanto caricare una copia

        coppia = await backup_repo.get_pair_by_backup_guild_id(guild.id)
        if coppia is None:
            await interaction.response.send_message(
                "⚠️ Questo server non risulta registrato come backup di nessun main — "
                "non c'è nulla da promuovere.",
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
            "👑 Questo server è stato promosso a **main**. Il vecchio main "
            f"(`{coppia.main_guild_id}`) non è più abbinato a questo backup. "
            "Per avere un nuovo backup: crea un server nuovo e lancia qui `/backup crea`.",
            ephemeral=True,
        )

    # ------------------------------------------------------------
    # Copie datate della struttura (M 12.17)
    # ------------------------------------------------------------
    @comando_di_gruppo("backup", nome="salva", descrizione="Salva una copia datata della struttura di questo server.")
    @app_commands.describe(
        nome="Nome della copia",
        ban="Salva anche la lista dei ban",
        membri="Salva anche nickname e ruoli dei membri",
        messaggi="Salva anche gli ultimi N messaggi di ogni canale di testo (0-100)",
    )
    async def salva(
        self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, 50],
        ban: bool = False, membri: bool = False, messaggi: app_commands.Range[int, 0, 100] = 0,
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
                await interaction.followup.send("⚠️ Mi serve il permesso «Banna membri» per leggere i ban.", ephemeral=True)
                return
        if membri:
            dati["membri"] = struttura.leggi_membri(guild)
        if messaggi:
            dati["messaggi"] = await self._ultimi_messaggi(guild, messaggi)
        if len(struttura.in_json(dati)) > struttura.MAX_FILE_BYTE:
            await interaction.followup.send("⚠️ La copia supera 10 MiB: salvala con meno messaggi o senza membri.", ephemeral=True)
            return
        copia_id = await backup_struttura_repo.salva_struttura(guild.id, nome, interaction.user.id, dati)
        if copia_id is None:
            await interaction.followup.send(
                f"⚠️ Ci sono già {MAX_COPIE_PER_SERVER} copie: eliminane una con /backup elimina.", ephemeral=True
            )
            return
        await registra_uso(guild.id, interaction.user.id, "salva", f"#{copia_id} {nome}")
        await interaction.followup.send(
            f"✅ Copia `#{copia_id}` salvata: {len(dati['ruoli'])} ruoli, {len(dati['canali'])} canali"
            + (f", {len(dati['ban'])} ban" if ban else "")
            + (f", {len(dati['membri'])} membri" if membri else "")
            + (f", {sum(len(m) for m in dati['messaggi'].values())} messaggi" if messaggi else "") + ".",
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

    @comando_di_gruppo("backup", nome="lista", descrizione="Le copie salvate di questo server, con la data.")
    async def lista(self, interaction: discord.Interaction) -> None:
        if not await self._puo(interaction, AZIONE_CREA):
            return
        copie = await backup_struttura_repo.lista_strutture(interaction.guild.id)
        if not copie:
            await interaction.response.send_message("Nessuna copia salvata: usa /backup salva.", ephemeral=True)
            return
        righe = [
            f"`#{c.id}` {'💬' if c.chat else '🏗️'} **{discord.utils.escape_markdown(c.nome)}** · "
            f"{discord.utils.format_dt(c.creato_il, 'f')}"
            + (f" · modello `{c.codice_modello}`" if c.codice_modello else "")
            for c in copie
        ]
        embed = discord.Embed(title="📦 Copie salvate", description="\n".join(righe)[:4000], color=discord.Color.blurple())
        embed.set_footer(text=f"Al massimo {MAX_COPIE_PER_SERVER} copie per server.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @comando_di_gruppo("backup", nome="carica", descrizione="Ricarica in questo server una copia salvata, scegliendo le parti.")
    @app_commands.describe(copia="Numero della copia (da /backup lista)")
    async def carica(self, interaction: discord.Interaction, copia: app_commands.Range[int, 1]) -> None:
        if not await self._puo(interaction, AZIONE_CARICA):
            return
        dati = await backup_struttura_repo.leggi_struttura(interaction.guild.id, copia)
        if dati is None:
            await interaction.response.send_message("Copia non trovata: guarda /backup lista.", ephemeral=True)
            return
        if dati.get("tipo") == "chat":
            await interaction.response.send_message("Questa è una chat salvata: usa /backup chat-carica.", ephemeral=True)
            return
        await interaction.response.send_message(
            f"Copia `#{copia}`: scegli cosa caricare. Ciò che esiste già (stesso nome) si riusa.",
            view=ScegliPartiView(self, interaction.user.id, dati, f"copia #{copia}"),
            ephemeral=True,
        )

    @comando_di_gruppo("backup", nome="elimina", descrizione="Elimina una copia salvata.")
    @app_commands.describe(copia="Numero della copia (da /backup lista)")
    async def elimina(self, interaction: discord.Interaction, copia: app_commands.Range[int, 1]) -> None:
        if not await self._puo(interaction, AZIONE_CREA):
            return
        if not await backup_struttura_repo.elimina_struttura(interaction.guild.id, copia):
            await interaction.response.send_message("Copia non trovata.", ephemeral=True)
            return
        await registra_uso(interaction.guild.id, interaction.user.id, "elimina", f"#{copia}")
        await interaction.response.send_message(f"🗑️ Copia `#{copia}` eliminata.", ephemeral=True)

    @comando_di_gruppo("backup", nome="stato", descrizione="Avanzamento dell'ultimo caricamento in questo server.")
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
            await interaction.response.send_message("Nessun caricamento in questo server.", ephemeral=True)
            return
        await interaction.response.send_message("\n".join(righe)[:1900], ephemeral=True)

    @comando_di_gruppo("backup", nome="annulla", descrizione="Ferma il caricamento in corso (ciò che è già fatto resta).")
    async def annulla(self, interaction: discord.Interaction) -> None:
        if not await self._puo(interaction, AZIONE_CARICA):
            return
        if not await backup_struttura_repo.chiedi_annullo(interaction.guild.id):
            await interaction.response.send_message("Nessun caricamento in corso.", ephemeral=True)
            return
        await registra_uso(interaction.guild.id, interaction.user.id, "annulla")
        await interaction.response.send_message("⏹️ Annullo chiesto: si ferma al prossimo passo.", ephemeral=True)

    # ------------------------------------------------------------
    # Modelli (NF-39)
    # ------------------------------------------------------------
    @comando_di_gruppo("backup", nome="modello", descrizione="Modelli: condividi una copia con un codice o carica quella di un altro server.")
    @app_commands.describe(
        azione="Cosa fare",
        copia="Per «pubblica» e «ritira»: numero della copia (da /backup lista)",
        codice="Per «usa»: il codice del modello",
    )
    @app_commands.choices(
        azione=[
            app_commands.Choice(name="Pubblica una copia come modello", value="pubblica"),
            app_commands.Choice(name="Usa un modello in questo server", value="usa"),
            app_commands.Choice(name="Ritira il codice di un modello", value="ritira"),
        ]
    )
    async def modello(
        self, interaction: discord.Interaction, azione: app_commands.Choice[str],
        copia: app_commands.Range[int, 1] | None = None,
        codice: app_commands.Range[str, 4, 32] | None = None,
    ) -> None:
        if not await self._puo(interaction, AZIONE_CARICA if azione.value == "usa" else AZIONE_CREA):
            return
        guild = interaction.guild
        if azione.value == "usa":
            trovato = await backup_struttura_repo.leggi_modello(codice.strip()) if codice else None
            if trovato is None:
                await interaction.response.send_message("Modello non trovato: controlla il codice.", ephemeral=True)
                return
            nome, dati = trovato
            await interaction.response.send_message(
                f"Modello «{discord.utils.escape_markdown(nome)}» (senza ban, membri e permessi dei singoli): "
                "scegli cosa caricare.",
                view=ScegliPartiView(self, interaction.user.id, struttura.senza_dati_personali(dati), f"modello {codice}"),
                ephemeral=True,
            )
            return
        if copia is None:
            await interaction.response.send_message("Scrivi il numero della copia nell'opzione «copia».", ephemeral=True)
            return
        if azione.value == "pubblica":
            nuovo = await backup_struttura_repo.pubblica_modello(guild.id, copia)
            testo = (
                f"🧩 Modello pronto: codice `{nuovo}`. Chi lo ha può caricarlo con /backup modello "
                "(ban, membri e permessi dei singoli non passano)." if nuovo else "Copia non trovata (le chat salvate non diventano modelli)."
            )
        else:
            nuovo = await backup_struttura_repo.ritira_modello(guild.id, copia)
            testo = "Codice ritirato: il modello non si può più usare." if nuovo else "Quella copia non è un modello."
        if nuovo:
            await registra_uso(guild.id, interaction.user.id, f"modello {azione.value}", f"#{copia}")
        await interaction.response.send_message(testo, ephemeral=True)

    # ------------------------------------------------------------
    # Sincronia di ban e ruoli (NF-39)
    # ------------------------------------------------------------
    @comando_di_gruppo("backup", nome="sincronia", descrizione="Tieni uguali ban e ruoli con un altro tuo server.")
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
            await interaction.response.send_message("⛔ La sincronia la gestisce solo l'owner del server.", ephemeral=True)
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
            await interaction.response.send_message("Scrivi l'ID dell'altro server nell'opzione «server».", ephemeral=True)
            return
        altro_id = int(server)
        if azione.value == "disattiva":
            fatto = await backup_sincronia_repo.disattiva(guild.id, altro_id)
            testo = "Sincronia disattivata." if fatto else "Nessuna sincronia con quel server."
        else:
            altro = self.bot.get_guild(altro_id)
            if altro is None:
                await interaction.response.send_message("Non sono in quel server: invitami prima.", ephemeral=True)
                return
            if not sync.stesso_proprietario(interaction.user.id, guild.owner_id, altro.owner_id):
                await interaction.response.send_message("⛔ Devi essere l'owner di entrambi i server.", ephemeral=True)
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
    @comando_di_gruppo("backup", nome="copia-canale", descrizione="Copia un canale con i permessi; una categoria con i suoi canali.")
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
            await interaction.followup.send("⚠️ Discord ha rifiutato la copia: controlla i miei permessi.", ephemeral=True)
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

    @comando_di_gruppo("backup", nome="copia-ruolo", descrizione="Copia un ruolo con i permessi e, a scelta, i permessi nei canali.")
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
            await interaction.followup.send("⚠️ Discord ha rifiutato la copia: controlla i miei permessi.", ephemeral=True)
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
    @comando_di_gruppo("backup", nome="chat-salva", descrizione="Salva gli ultimi messaggi di un canale (fino a 1000) per ricaricarli dopo.")
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
            await interaction.response.send_message("Scegli un canale di testo.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            messaggi = await leggi_chat(canale, quanti)
        except discord.HTTPException:
            await interaction.followup.send("⚠️ Non riesco a leggere quel canale: controlla i miei permessi.", ephemeral=True)
            return
        dati = {"versione": struttura.VERSIONE, "tipo": "chat", "canale": canale.name, "messaggi": messaggi}
        if len(struttura.in_json(dati)) > struttura.MAX_FILE_BYTE:
            await interaction.followup.send("⚠️ Troppi dati: salva meno messaggi.", ephemeral=True)
            return
        copia_id = await backup_struttura_repo.salva_struttura(
            interaction.guild.id, nome or f"chat #{canale.name}"[:50], interaction.user.id, dati
        )
        if copia_id is None:
            await interaction.followup.send(
                f"⚠️ Ci sono già {MAX_COPIE_PER_SERVER} copie: eliminane una con /backup elimina.", ephemeral=True
            )
            return
        await registra_uso(interaction.guild.id, interaction.user.id, "chat-salva", f"#{copia_id} {canale.name}")
        await interaction.followup.send(
            f"✅ Chat salvata come copia `#{copia_id}`: {len(messaggi)} messaggi. "
            "Gli allegati si ricaricano come file finché il loro link vale (circa un giorno), poi come link.",
            ephemeral=True,
        )

    @comando_di_gruppo("backup", nome="chat-carica", descrizione="Ricarica una chat salvata in un canale, anche diverso.")
    @app_commands.describe(copia="Numero della chat salvata (da /backup lista)", canale="Canale dove ricaricarla (se vuoto, questo)")
    async def chat_carica(
        self, interaction: discord.Interaction, copia: app_commands.Range[int, 1],
        canale: discord.TextChannel | None = None,
    ) -> None:
        if not await self._puo(interaction, AZIONE_CARICA):
            return
        canale = canale or interaction.channel
        dati = await backup_struttura_repo.leggi_struttura(interaction.guild.id, copia)
        if dati is None or dati.get("tipo") != "chat":
            await interaction.response.send_message("Chat salvata non trovata: guarda /backup lista.", ephemeral=True)
            return
        if not isinstance(canale, discord.TextChannel):
            await interaction.response.send_message("Scegli un canale di testo.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            webhook = await webhook_chat(canale)
        except discord.HTTPException:
            webhook = None
        if webhook is None:
            await interaction.followup.send(
                "⚠️ Non posso usare un webhook in quel canale: serve «Gestisci webhook» e meno di 15 webhook.",
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
    @comando_di_gruppo("backup", nome="esporta", descrizione="Esporta struttura, canali, ruoli, ban o reazioni in un file.")
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
            await interaction.followup.send("⚠️ Discord ha rifiutato la lettura: controlla i miei permessi.", ephemeral=True)
            return
        if isinstance(righe, str):
            await interaction.followup.send(righe, ephemeral=True)
            return
        tipo_csv = "canali" if tipo == "canale" else "ruoli" if tipo == "ruolo" else tipo
        contenuto, estensione = struttura.esporta(tipo_csv, formato.value if formato else "json", righe)
        if len(contenuto) > struttura.MAX_FILE_BYTE:
            await interaction.followup.send("⚠️ Il file supera 10 MiB.", ephemeral=True)
            return
        await registra_uso(guild.id, interaction.user.id, "esporta", tipo)
        await interaction.followup.send(
            f"📄 Esportazione «{cosa.name}».",
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

    @comando_di_gruppo("backup", nome="importa", descrizione="Importa la struttura da un file JSON, scegliendo cosa applicare.")
    @app_commands.describe(file="File JSON esportato con /backup esporta (al massimo 10 MiB)")
    async def importa(self, interaction: discord.Interaction, file: discord.Attachment) -> None:
        if not await self._puo(interaction, AZIONE_CARICA):
            return
        if file.size > struttura.MAX_FILE_BYTE:
            await interaction.response.send_message("⚠️ Il file supera 10 MiB.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            contenuto = await file.read()
        except discord.HTTPException:
            await interaction.followup.send("⚠️ Non riesco a leggere il file: riprova.", ephemeral=True)
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
            "File valido: scegli cosa caricare. Ciò che esiste già (stesso nome) si riusa.",
            view=ScegliPartiView(self, interaction.user.id, dati, f"file {file.filename[:60]}"),
            ephemeral=True,
        )

    # ------------------------------------------------------------
    # Permessi e registro (BKP-018, BKP-019)
    # ------------------------------------------------------------
    @comando_di_gruppo("backup", nome="permessi", descrizione="Chi può creare e chi può caricare i backup (solo l'owner).")
    @app_commands.describe(livello="Chi può fare cosa")
    @app_commands.choices(livello=[app_commands.Choice(name=v, value=k) for k, v in LIVELLI.items()])
    async def permessi(self, interaction: discord.Interaction, livello: app_commands.Choice[str]) -> None:
        guild = interaction.guild
        if guild is None or interaction.user.id != guild.owner_id:
            await interaction.response.send_message("⛔ Solo l'owner del server sceglie il livello.", ephemeral=True)
            return
        await db.set_guild_setting(guild.id, SETTING_LIVELLO, livello.value)
        await registra_uso(guild.id, interaction.user.id, "permessi", livello.value)
        await interaction.response.send_message(f"✅ Backup: «{livello.name}».", ephemeral=True)

    @comando_di_gruppo("backup", nome="registro", descrizione="Chi ha usato backup, modelli e sincronie (ultimi 20, 365 giorni).")
    async def registro(self, interaction: discord.Interaction) -> None:
        if not await self._puo(interaction, AZIONE_CREA):
            return
        righe = await backup_struttura_repo.leggi_registro(interaction.guild.id)
        if not righe:
            await interaction.response.send_message("Registro vuoto.", ephemeral=True)
            return
        testo = "\n".join(
            f"{discord.utils.format_dt(r['creato_il'], 'd')} <@{r['user_id']}> **{r['azione']}** "
            f"{discord.utils.escape_markdown(r['dettaglio'])}"
            for r in righe
        )
        embed = discord.Embed(title="📜 Registro del backup", description=testo[:4000], color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BackupCog(bot))
