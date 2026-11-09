"""
cogs/utility/custom_commands.py
===============================
Comandi personalizzati del server, detti tag (NF-09, SPEC §22.5): un nome,
un testo o un embed, un ruolo da dare o togliere, una pausa. Si usano con
`/tag usa` e, se l'admin sceglie un prefisso, anche scrivendo
`<prefisso>nome` (usa guild_config.prefix, M 10.15). Si gestiscono con
`/admin-tag tag crea|modifica|elimina|elenco|prefisso`.
Funzioni coperte: SPEC §22 (NF-09)
"""

from __future__ import annotations

import logging
import time
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.admin_mentions_logic import menzioni_ammesse, utente_puo_pingare_ruoli
from core.bounded_cache import BoundedCache
from core.command_access import Livello, autocomplete_protetto
from core.command_groups import CogConGruppi, SOTTOGRUPPI, comando_di_gruppo
from core.custom_command_logic import (
    MAX_ARGOMENTI,
    MAX_NOME,
    MAX_PAUSA,
    MAX_TAG,
    MAX_TESTO,
    AZIONE_CANCELLA_RISPOSTA,
    azione_ruolo,
    costruisci_risposta,
    dividi_testo,
    e_nuovo_innesco,
    ha_il_permesso,
    scegli_pesata,
    nome_da_messaggio,
    pausa_residua,
    valida_prefisso,
)
from core.database import db
from core import tag_script_logic as tag_script
from core.i18n import testo_guild, testo_per
from core.repositories.tag_inneschi_repo import tag_inneschi_repo
from core.repositories.tag_script_repo import massimo_chiavi, tag_script_repo
from core.tag_script_logic import ha_script
from core.tag_eliminazione import pulisci_tag_eliminato
from core.nome_logic import normalizza_nome
from core.lista_limiti_logic import righe_entro_limite
from core.premium import PremiumModule, registry
from core.repositories.custom_command_repo import custom_command_repo
from core.scheduler import in_seconds, scheduler
from core.role_safety import check_role_assignable, motivo_ruolo_automatico_non_assegnabile

logger = logging.getLogger("iyokai.custom_commands")

MODULE_CUSTOM_COMMANDS = "custom_commands"

_SG_COMANDI = ("comandi", "Comandi personalizzati e risposte automatiche")
TESTO_VUOTO = "(il comando non ha prodotto nessun testo)"
_TTL_PREFISSO = 60  # secondi: il prefisso si rilegge ogni minuto, non a ogni messaggio

# (server, nome, utente) -> ultimo uso; (server) -> (prefisso, scadenza)
_ultimo_uso: BoundedCache[tuple[int, str, int], datetime] = BoundedCache(max_size=20_000)
_cache_prefissi: BoundedCache[int, tuple[str | None, float]] = BoundedCache(max_size=5_000)

_SCELTE_AZIONE = [
    app_commands.Choice(name="nessuna", value="nessuna"),
    app_commands.Choice(name="dai il ruolo", value="dai"),
    app_commands.Choice(name="togli il ruolo", value="togli"),
    app_commands.Choice(name="alterna", value="alterna"),
]


class CustomCommandsCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ================================================================
    # Uso
    # ================================================================
    async def _prefisso(self, guild_id: int) -> str | None:
        voce = _cache_prefissi.get(guild_id)
        ora = time.monotonic()
        if voce is not None and voce[1] > ora:
            return voce[0]
        prefisso = await custom_command_repo.get_prefix(guild_id)
        _cache_prefissi.set(guild_id, (prefisso, ora + _TTL_PREFISSO))
        return prefisso

    async def _prepara(self, tag, membro: discord.Member, canale, argomenti: str, bersaglio: discord.abc.User | None = None,
                       ruolo: bool = True):
        """(testo, nota sul ruolo): applica il ruolo del tag (se `ruolo`) e costruisce la risposta (una a caso se ce ne sono con peso)."""
        nota = await self._applica_ruolo(tag, membro) if ruolo else None
        base = scegli_pesata(await custom_command_repo.get_risposte(tag.guild_id, tag.name)) or tag.response
        valori = {
            "user": membro.mention,
            "username": membro.display_name,
            "server": membro.guild.name,
            "channel": getattr(canale, "mention", ""),
            "args": argomenti,
            "bersaglio": bersaglio.mention if bersaglio is not None else "",
        }
        if ha_script(base):
            autore = getattr(tag, "created_by", None)
            creatore = membro.guild.get_member(autore) if autore else None
            staff = creatore is not None and creatore.guild_permissions.manage_guild
            archivio = tag_script_repo.archivio(tag.guild_id, lambda: massimo_chiavi(tag.guild_id, self.bot), autore=autore,
                                                massimo_autore=None if staff else tag_script.MAX_CHIAVI_AUTORE)
            esito = await tag_script.esegui(base, tag_script.Contesto(valori=valori, adesso=datetime.now(ZoneInfo("Europe/Rome")), archivio=archivio))
            if esito.errore is not None:
                logger.info("Tag %s: script fermato (%s).", tag.name, esito.errore.chiave)
                try:
                    await tag_script_repo.registra_errore(tag.guild_id, tag.name, esito.errore.chiave, esito.errore.dettaglio)
                except Exception:
                    logger.warning("Errore dello script del tag %s non registrato.", tag.name, exc_info=True)
                return await testo_guild(membro.guild, "tag_script_fermato", nome=tag.name), nota
            base = esito.testo
        return costruisci_risposta(base, valori).strip() or TESTO_VUOTO, nota

    @staticmethod
    def _rifiuto(tag, membro: discord.Member, canale, bersaglio) -> str | None:
        """La chiave del testo se il tag non si può usare qui: permesso, canale NSFW, bersaglio mancante."""
        if not ha_il_permesso(membro.guild_permissions, tag.permesso):
            return "tag_manca_permesso"
        if tag.solo_nsfw and not (hasattr(canale, "is_nsfw") and canale.is_nsfw()):
            return "tag_solo_nsfw"
        if tag.bersaglio and bersaglio is None:
            return "tag_serve_bersaglio"
        if tag.cancella_messaggi and not (hasattr(canale, "permissions_for") and canale.permissions_for(membro).manage_messages):
            return "tag_serve_gestire_messaggi"  # chi pulisce il canale deve poterlo fare da solo
        return None

    @staticmethod
    async def _rifiuto_gruppo(tag, membro: discord.Member, canale) -> str | None:
        """Le regole del gruppo del tag: un solo canale e/o un ruolo richiesto."""
        if not tag.gruppo:
            return None
        regole = await custom_command_repo.gruppo(tag.guild_id, tag.gruppo)
        if regole is None:
            return None
        if regole["canale_id"] and getattr(canale, "id", None) != regole["canale_id"]:
            return "tag_gruppo_canale"
        if regole["ruolo_id"] and regole["ruolo_id"] not in {r.id for r in membro.roles} and not membro.guild_permissions.administrator:
            return "tag_gruppo_ruolo"
        return None

    @staticmethod
    def _destinazione(tag, membro: discord.Member, canale):
        """(dove scrivere, se la risposta va tenuta fuori dal canale). «altro» senza canale valido torna nel canale."""
        if tag.invio == "privato":
            return membro, True
        if tag.invio == "altro" and tag.canale_id:
            altro = membro.guild.get_channel(tag.canale_id)
            if isinstance(altro, discord.abc.Messageable) and altro.permissions_for(membro.guild.me).send_messages:
                return altro, True
        return canale, False

    @staticmethod
    async def _manda(invia, tag, testo: str):
        """Manda il testo (diviso in due se supera 2.000 caratteri; embed fino a 4.096). Mette le reazioni e prenota la
        cancellazione se il tag la chiede. Ritorna l'ultimo messaggio."""
        menzioni = menzioni_ammesse(tag.ping_ruoli)
        if tag.use_embed:
            inviati = [await invia(embed=discord.Embed(description=testo[:4096]), allowed_mentions=menzioni)]
        else:
            inviati = [await invia(pezzo, allowed_mentions=menzioni) for pezzo in dividi_testo(testo)]
        for messaggio in inviati:
            if messaggio is None:
                continue
            for emoji in tag.reazioni or ():
                try:
                    await messaggio.add_reaction(emoji)
                except discord.HTTPException:
                    break  # emoji non valida o permesso tolto: il tag ha risposto lo stesso
            if tag.si_cancella_dopo:
                try:
                    await scheduler.schedule(
                        tag.guild_id, 0, AZIONE_CANCELLA_RISPOSTA, in_seconds(tag.si_cancella_dopo),
                        {"channel_id": messaggio.channel.id, "message_id": messaggio.id})
                except Exception:
                    logger.warning("Cancellazione del tag %s non prenotata.", tag.name, exc_info=True)
        return inviati[-1] if inviati else None

    async def handle_cancella_risposta(self, guild_id: int, user_id: int, payload: dict) -> None:
        """Handler dello scheduler: cancella la risposta di un tag. Se è già sparita non c'è niente da fare."""
        canale = self.bot.get_channel(payload.get("channel_id", 0))
        if canale is None:
            return
        try:
            await canale.get_partial_message(payload["message_id"]).delete()
        except discord.NotFound:
            return

    async def _pulisci_canale(self, tag, canale, prima_di: int) -> None:
        """Cancella gli ultimi N messaggi del canale (non fissati, più giovani di 14 giorni) prima del comando."""
        limite = datetime.now(timezone.utc) - timedelta(days=14, minutes=-5)
        try:
            await canale.purge(limit=tag.cancella_messaggi, before=discord.Object(id=prima_di), bulk=True,
                               check=lambda m: not m.pinned and m.created_at > limite, reason=f"Tag {tag.name}")
        except discord.HTTPException:
            logger.warning("Tag %s: pulizia del canale %s non riuscita.", tag.name, getattr(canale, "id", None))

    async def _applica_ruolo(self, tag, membro: discord.Member) -> str | None:
        if tag.role_id is None or tag.role_action == "nessuna":
            return None
        motivo = motivo_ruolo_automatico_non_assegnabile(membro.guild, tag.role_id)
        if motivo is not None:
            logger.warning("Tag %s: ruolo %s non assegnabile: %s", tag.name, tag.role_id, motivo)
            return "Il ruolo di questo comando non può essere assegnato: avvisa lo staff."
        ruolo = membro.guild.get_role(tag.role_id)
        mossa = azione_ruolo(tag.role_action, ruolo in membro.roles)
        try:
            if mossa == "dai":
                await membro.add_roles(ruolo, reason=f"Comando personalizzato {tag.name}")
            elif mossa == "togli":
                await membro.remove_roles(ruolo, reason=f"Comando personalizzato {tag.name}")
        except discord.HTTPException:
            return "Non sono riuscito a cambiare il ruolo."
        return None

    @staticmethod
    def _pausa(tag, guild_id: int, user_id: int) -> float:
        chiave = (guild_id, tag.name, user_id)
        ora = datetime.now(timezone.utc)
        residuo = pausa_residua(_ultimo_uso.get(chiave), ora, tag.cooldown_seconds)
        if residuo == 0 and tag.cooldown_seconds > 0:
            _ultimo_uso.set(chiave, ora)
        return residuo

    @commands.Cog.listener()
    async def on_message_edit(self, prima: discord.Message, dopo: discord.Message) -> None:
        """Un messaggio modificato in un comando fa scattare il tag solo se il tag lo ha chiesto (anche_modificati)."""
        if dopo.author.bot or dopo.guild is None or not dopo.content or prima.content == dopo.content:
            return
        if datetime.now(timezone.utc) - dopo.created_at > timedelta(minutes=10):
            return
        prefisso = await self._prefisso(dopo.guild.id)
        if not e_nuovo_innesco(prima.content, dopo.content, prefisso):
            return
        await self.on_message(dopo, dalla_modifica=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message, dalla_modifica: bool = False) -> None:
        if message.author.bot or message.guild is None or not message.content:
            return
        if not await db.is_module_active_for_guild(message.guild.id, MODULE_CUSTOM_COMMANDS):
            return
        prefisso = await self._prefisso(message.guild.id)
        trovato = nome_da_messaggio(message.content, prefisso)
        if trovato is None:
            return
        nome, argomenti = trovato
        tag = await custom_command_repo.get_tag(message.guild.id, nome)
        if tag is None or (dalla_modifica and not tag.anche_modificati):
            return
        if self._rifiuto(tag, message.author, message.channel, message.mentions[0] if message.mentions else None) is not None \
                or await self._rifiuto_gruppo(tag, message.author, message.channel) is not None:
            return  # col prefisso si tace: niente messaggi di servizio nel canale
        if self._pausa(tag, message.guild.id, message.author.id) > 0:
            return
        bersaglio = message.mentions[0] if message.mentions else None
        testo, nota = await self._prepara(tag, message.author, message.channel, argomenti[:MAX_ARGOMENTI], bersaglio)
        dest, fuori = self._destinazione(tag, message.author, message.channel)
        if tag.cancella_messaggi:
            await self._pulisci_canale(tag, message.channel, message.id)
        try:
            await self._manda(dest.send, tag, testo)
        except discord.HTTPException:
            logger.warning("Tag %s: invio fallito nel canale %s", nome, message.channel.id)
            return
        if tag.cancella_innesco:
            try:
                await message.delete()
            except discord.HTTPException:
                pass  # al bot può mancare «Gestire i messaggi»: il tag ha risposto lo stesso
        await custom_command_repo.add_use(message.guild.id, nome)

    async def esegui_innesco(self, guild: discord.Guild, nome: str, canale, *, membro: discord.Member | None = None) -> str | None:
        """Fa partire il tag `nome` per un innesco (B27). `membro` è chi l'ha fatto scattare (reazione, ruolo, bottone); a tempo
        è None e parla il bot, senza toccare ruoli. Ritorna la chiave del motivo se il tag non può partire, altrimenti None."""
        tag = await custom_command_repo.get_tag(guild.id, nome)
        if tag is None:
            return "inn_tag_manca"
        if tag.solo_nsfw and not (hasattr(canale, "is_nsfw") and canale.is_nsfw()):
            return "tag_solo_nsfw"
        if membro is not None:
            rifiuto = self._rifiuto(tag, membro, canale, None) or await self._rifiuto_gruppo(tag, membro, canale)
            if rifiuto is not None:
                return rifiuto
            if self._pausa(tag, guild.id, membro.id) > 0:
                return "inn_pausa"
        if not canale.permissions_for(guild.me).send_messages:
            return "inn_canale_senza_permesso"
        testo, _ = await self._prepara(tag, membro or guild.me, canale, "", None, ruolo=membro is not None)
        dest = self._destinazione(tag, membro, canale)[0] if membro is not None else canale
        try:
            await self._manda(dest.send, tag, testo)
        except discord.HTTPException:
            logger.warning("Innesco del tag %s: invio fallito nel canale %s", nome, getattr(canale, "id", None))
            return "tag_invio_fallito"
        await custom_command_repo.add_use(guild.id, nome)
        return None

    async def _nomi_per_completamento(self, interaction: discord.Interaction, current: str):
        if interaction.guild is None:
            return []
        nomi = await custom_command_repo.search_names(interaction.guild.id, current.lower(), 25)
        return [app_commands.Choice(name=n, value=n) for n in nomi]

    async def _completa_uso(self, interaction: discord.Interaction, current: str):
        return await self._nomi_per_completamento(interaction, current)

    @autocomplete_protetto(Livello.ADMIN)
    async def _completa_admin(self, interaction: discord.Interaction, current: str):
        return await self._nomi_per_completamento(interaction, current)

    @comando_di_gruppo(
        "tag",
        nome="usa",
        descrizione="Usa un comando personalizzato di questo server.",
    )
    @app_commands.describe(nome="Il comando da usare", argomenti="Testo da passare al comando (facoltativo)",
                           bersaglio="Il membro a cui è rivolto, se il tag lo chiede")
    @app_commands.autocomplete(nome=_completa_uso)
    async def tag(
        self,
        interaction: discord.Interaction,
        nome: app_commands.Range[str, 1, MAX_NOME],
        argomenti: app_commands.Range[str, 0, MAX_ARGOMENTI] = "",
        bersaglio: discord.Member | None = None,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                await testo_per(interaction, "guild_only_command"), ephemeral=True
            )
            return
        if not await db.is_module_active_for_guild(guild.id, MODULE_CUSTOM_COMMANDS):
            await interaction.response.send_message(
                await testo_per(interaction, "module_not_active"), ephemeral=True
            )
            return
        normalizzato = normalizza_nome(nome)
        tag = await custom_command_repo.get_tag(guild.id, normalizzato) if normalizzato else None
        if tag is None:
            await interaction.response.send_message(
                await testo_per(interaction, "customcomman_questo_server_non_ha_un"), ephemeral=True
            )
            return
        residuo = self._pausa(tag, guild.id, interaction.user.id)
        if residuo > 0:
            await interaction.response.send_message(
                await testo_per(interaction, "customcomman_aspetta_ancora_secondi_prima_di", v1=int(residuo) + 1), ephemeral=True
            )
            return
        rifiuto = self._rifiuto(tag, interaction.user, interaction.channel, bersaglio) \
            or await self._rifiuto_gruppo(tag, interaction.user, interaction.channel)
        if rifiuto is not None:
            await interaction.response.send_message(await testo_per(interaction, rifiuto), ephemeral=True)
            return
        # Dare o togliere il ruolo sono chiamate a Discord che possono superare i 3 secondi
        # concessi per rispondere: si prenota la risposta prima.
        dest, fuori = self._destinazione(tag, interaction.user, interaction.channel)
        await interaction.response.defer(ephemeral=fuori)
        if tag.cancella_messaggi:
            await self._pulisci_canale(tag, interaction.channel, interaction.id)
        testo, nota = await self._prepara(tag, interaction.user, interaction.channel, argomenti, bersaglio)
        try:
            await self._manda(dest.send if fuori else interaction.followup.send, tag, testo)
        except discord.HTTPException:
            await interaction.followup.send(await testo_per(interaction, "tag_invio_fallito"), ephemeral=True)
            return
        if fuori:
            await interaction.followup.send(await testo_per(interaction, "tag_inviato_privato" if tag.invio == "privato" or dest is interaction.user else "tag_inviato_altro"), ephemeral=True)
        if nota:
            await interaction.followup.send(nota, ephemeral=True)
        await custom_command_repo.add_use(guild.id, tag.name)

    # ================================================================
    # Gestione (admin)
    # ================================================================
    async def _pronto(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(
                await testo_per(interaction, "guild_only_command"), ephemeral=True
            )
            return False
        if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_CUSTOM_COMMANDS):
            await interaction.response.send_message(
                await testo_per(interaction, "ping_questo_modulo_non_attivo_su"),
                ephemeral=True,
            )
            return False
        return True

    @staticmethod
    async def _controlla_ruolo(interaction, ruolo, azione) -> bool:
        if (ruolo is None) != (azione == "nessuna"):
            await interaction.response.send_message(
                await testo_per(interaction, "customcomman_ruolo_azione_vanno_insieme_scegli"),
                ephemeral=True,
            )
            return False
        if ruolo is not None:
            motivo = check_role_assignable(interaction.guild, ruolo, interaction.user, self_service=True)
            if motivo is not None:
                await interaction.response.send_message(motivo, ephemeral=True)
                return False
        return True

    @comando_di_gruppo("admin-tag", nome="crea", descrizione="Crea un comando personalizzato.", sottogruppo=SOTTOGRUPPI["admin-tag tag"])
    @app_commands.describe(
        nome=f"Il nome (lettere minuscole, cifre, - e _; massimo {MAX_NOME})",
        testo="La risposta. Segnaposto: {user} {username} {server} {channel} {args}",
        come_embed="Mandare la risposta come embed?",
        ruolo="Ruolo da dare o togliere a chi lo usa",
        azione="Cosa fare col ruolo",
        pausa_secondi="Pausa tra un uso e l'altro, per ogni utente",
    )
    @app_commands.choices(azione=_SCELTE_AZIONE)
    async def crea(
        self,
        interaction: discord.Interaction,
        nome: app_commands.Range[str, 1, MAX_NOME],
        testo: app_commands.Range[str, 1, MAX_TESTO],
        come_embed: bool = False,
        ruolo: discord.Role | None = None,
        azione: str = "nessuna",
        pausa_secondi: app_commands.Range[int, 0, MAX_PAUSA] = 0,
    ) -> None:
        if not await self._pronto(interaction):
            return
        normalizzato = normalizza_nome(nome)
        if normalizzato is None:
            await interaction.response.send_message(
                await testo_per(interaction, "forms_il_nome_puo_avere_solo"), ephemeral=True
            )
            return
        if not await self._controlla_ruolo(interaction, ruolo, azione):
            return
        esito = await custom_command_repo.create_tag(
            interaction.guild.id,
            normalizzato,
            response=testo,
            use_embed=come_embed,
            role_id=ruolo.id if ruolo else None,
            role_action=azione,
            cooldown_seconds=pausa_secondi,
            ping_ruoli=utente_puo_pingare_ruoli(interaction.user),
            created_by=interaction.user.id,
        )
        messaggi = {
            "ok": f"Comando `{normalizzato}` creato. Si usa con `/tag usa`.",
            "esiste": f"Esiste già un comando `{normalizzato}`: usa `/admin-tag tag modifica`.",
            "pieno": f"Questo server ha già {MAX_TAG} comandi personalizzati: eliminane uno.",
        }
        await interaction.response.send_message(messaggi[esito], ephemeral=True)

    @comando_di_gruppo("admin-tag", nome="modifica", descrizione="Cambia un comando personalizzato.", sottogruppo=SOTTOGRUPPI["admin-tag tag"])
    @app_commands.describe(
        nome="Il comando da cambiare",
        testo="Nuova risposta",
        come_embed="Mandare la risposta come embed?",
        ruolo="Nuovo ruolo (serve anche l'azione)",
        azione="Cosa fare col ruolo (\"nessuna\" toglie il ruolo dal comando)",
        pausa_secondi="Nuova pausa tra un uso e l'altro",
    )
    @app_commands.choices(azione=_SCELTE_AZIONE)
    @app_commands.autocomplete(nome=_completa_admin)
    async def modifica(
        self,
        interaction: discord.Interaction,
        nome: app_commands.Range[str, 1, MAX_NOME],
        testo: app_commands.Range[str, 1, MAX_TESTO] | None = None,
        come_embed: bool | None = None,
        ruolo: discord.Role | None = None,
        azione: str | None = None,
        pausa_secondi: app_commands.Range[int, 0, MAX_PAUSA] | None = None,
    ) -> None:
        if not await self._pronto(interaction):
            return
        normalizzato = normalizza_nome(nome)
        campi: dict = {}
        if testo is not None:
            campi["response"] = testo
            campi["ping_ruoli"] = utente_puo_pingare_ruoli(interaction.user)
        if come_embed is not None:
            campi["use_embed"] = come_embed
        if pausa_secondi is not None:
            campi["cooldown_seconds"] = pausa_secondi
        if azione is not None:
            if not await self._controlla_ruolo(interaction, ruolo, azione):
                return
            campi["role_id"] = ruolo.id if ruolo else None
            campi["role_action"] = azione
        elif ruolo is not None:
            await interaction.response.send_message(await testo_per(interaction, "customcomman_se_scegli_un_ruolo_scegli"), ephemeral=True)
            return
        if not campi or normalizzato is None:
            await interaction.response.send_message(await testo_per(interaction, "customcomman_non_hai_indicato_nulla_da"), ephemeral=True)
            return
        fatto = await custom_command_repo.update_tag(interaction.guild.id, normalizzato, **campi)
        await interaction.response.send_message(
            await testo_per(interaction, "customcomman_comando_aggiornato") if fatto else await testo_per(interaction, "customcomman_non_esiste_un_comando_con"), ephemeral=True
        )

    @comando_di_gruppo("admin-tag", nome="elimina", descrizione="Elimina un comando personalizzato.", sottogruppo=SOTTOGRUPPI["admin-tag tag"])
    @app_commands.describe(nome="Il comando da eliminare")
    @app_commands.autocomplete(nome=_completa_admin)
    async def elimina(self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, MAX_NOME]) -> None:
        if not await self._pronto(interaction):
            return
        normalizzato = normalizza_nome(nome)
        fatto = normalizzato is not None and await custom_command_repo.delete_tag(interaction.guild.id, normalizzato)
        if fatto:
            await pulisci_tag_eliminato(self.bot, interaction.guild.id, normalizzato)
        await interaction.response.send_message(
            await testo_per(interaction, "customcomman_comando_eliminato") if fatto else await testo_per(interaction, "customcomman_non_esiste_un_comando_con"), ephemeral=True
        )

    @comando_di_gruppo("admin-tag", nome="elenco", descrizione="Mostra i comandi personalizzati del server.", sottogruppo=SOTTOGRUPPI["admin-tag tag"])
    async def elenco(self, interaction: discord.Interaction) -> None:
        if not await self._pronto(interaction):
            return
        tag = await custom_command_repo.list_tags(interaction.guild.id)
        prefisso = await custom_command_repo.get_prefix(interaction.guild.id)
        righe = [f"`{t.name}` — {t.uses} usi" for t in tag] or ["Nessun comando personalizzato."]
        testo, _ = righe_entro_limite(righe, 3800)
        piede = f"\n\nPrefisso: `{prefisso}`" if prefisso else "\n\nPrefisso: nessuno (solo `/tag usa`)."
        embed = discord.Embed(title=await testo_per(interaction, "customcomman_comandi_personalizzati", v1=len(tag), v2=MAX_TAG), description=testo + piede)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @comando_di_gruppo("admin-tag", nome="prefisso", descrizione="Scegli il prefisso per usare i comandi scrivendo nel canale.", sottogruppo=SOTTOGRUPPI["admin-tag tag"])
    @app_commands.describe(simbolo="1-3 simboli, per esempio ! — lascia vuoto per spegnere il prefisso")
    async def prefisso(self, interaction: discord.Interaction, simbolo: app_commands.Range[str, 0, 3] = "") -> None:
        if not await self._pronto(interaction):
            return
        if simbolo == "":
            await custom_command_repo.set_prefix(interaction.guild.id, None)
            _cache_prefissi.set(interaction.guild.id, (None, time.monotonic() + _TTL_PREFISSO))
            await interaction.response.send_message(await testo_per(interaction, "customcomman_prefisso_spento_comandi_si_usano"), ephemeral=True)
            return
        errore = valida_prefisso(simbolo)
        if errore is not None:
            await interaction.response.send_message(errore, ephemeral=True)
            return
        await custom_command_repo.set_prefix(interaction.guild.id, simbolo)
        _cache_prefissi.set(interaction.guild.id, (simbolo, time.monotonic() + _TTL_PREFISSO))
        await interaction.response.send_message(
            await testo_per(interaction, "customcomman_prefisso_attivo_scrivendo_nome_parte", simbolo=simbolo), ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_CUSTOM_COMMANDS,
            display_name="Comandi personalizzati",
            category="utility",
            description="Comandi creati dal server: testo o embed, ruolo, pausa; uso con /tag usa o col prefisso.",
            premium_capable=False,
        )
    )
    cog = CustomCommandsCog(bot)
    await bot.add_cog(cog)
    scheduler.register_handler(AZIONE_CANCELLA_RISPOSTA, cog.handle_cancella_risposta)
