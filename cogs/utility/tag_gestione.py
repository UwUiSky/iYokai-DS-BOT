"""
cogs/utility/tag_gestione.py
============================
Tag di chi non è staff e strumenti dello staff per tutti i tag: `/tag crea|modifica|elimina|prendi` (solo i propri; crea
solo con il ruolo scelto dal server), `/admin-tag tag creatori|sostituisci|esporta|importa|gruppi`. I pacchetti si condividono
con un codice (7 giorni) o un file JSON (1 MiB); non portano ruoli né canali.
Funzioni coperte: catalogo #128 UTL-034, 035, 039, 040, 041, 042 (D69, B21)
"""

from __future__ import annotations

import io
import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.command_access import Livello, autocomplete_protetto, puo_usare
from core.command_groups import CogConGruppi, SOTTOGRUPPI, comando_di_gruppo
from core.config_impostazioni import imposta_impostazione
from core.custom_command_logic import MAX_NOME, MAX_TAG
from core.database import db
from core.i18n import testo_per
from core.nome_logic import normalizza_nome
from core.repositories.custom_command_repo import custom_command_repo
from core.repositories.tag_inneschi_repo import tag_inneschi_repo
from core.tag_pacchetti_logic import (
    MAX_BYTE_PACCHETTO, PacchettoErrato, leggi_pacchetto, nome_gruppo_valido, nuovo_codice, pacchetto_da_tag, pacchetto_in_file,
)
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.tag_gestione")

MODULE_CUSTOM_COMMANDS = "custom_commands"
SETTING_RUOLO_CREATORI = "tag_ruolo_creatori"
MAX_TAG_PER_CREATORE = 10
MAX_TESTO_PUBBLICO = 2000
SECONDI_CONFERMA = 60
_NESSUNA_MENZIONE = discord.AllowedMentions.none()
_SCELTE_FORMATO = [app_commands.Choice(name="codice (vale 7 giorni)", value="codice"), app_commands.Choice(name="file JSON", value="file")]
_SCELTE_GRUPPO = [app_commands.Choice(name=n, value=v) for n, v in (("imposta o cambia", "imposta"), ("togli", "togli"), ("elenco", "elenco"))]


class ConfermaSostituisci(BaseView):
    """La sostituzione cambia più tag insieme: conferma di chi ha dato il comando, livello ricontrollato al tasto."""

    def __init__(self, proprietario: int, guild_id: int, da: str, a: str, etichette: tuple[str, str]) -> None:
        super().__init__(timeout=SECONDI_CONFERMA)
        self.proprietario, self.guild_id, self.da, self.a = proprietario, guild_id, da, a
        self.conferma.label, self.annulla.label = etichette[0][:80], etichette[1][:80]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        if interaction.user.id != self.proprietario:
            await interaction.response.send_message(await testo_per(interaction, "conteggio_non_e_tuo"), ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Conferma", style=discord.ButtonStyle.danger)
    async def conferma(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()  # anti-doppio-clic prima di ogni await
        if not await puo_usare(interaction, Livello.ADMIN):
            await interaction.response.edit_message(content=await testo_per(interaction, "conteggio_non_e_tuo"), view=None)
            return
        quanti = await custom_command_repo.sostituisci(self.guild_id, self.da, self.a, True)
        await interaction.response.edit_message(content=await testo_per(interaction, "tag_sostituiti", quanti=quanti), view=None)

    @discord.ui.button(label="Annulla", style=discord.ButtonStyle.secondary)
    async def annulla(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(content=await testo_per(interaction, "conteggio_togli_annullato"), view=None)


class TagGestioneCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _pronto(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return False
        if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_CUSTOM_COMMANDS):
            await interaction.response.send_message(await testo_per(interaction, "ping_questo_modulo_non_attivo_su"), ephemeral=True)
            return False
        return True

    async def _dire(self, interaction: discord.Interaction, chiave: str, **valori) -> None:
        await interaction.response.send_message(await testo_per(interaction, chiave, **valori), ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE)

    async def _miei(self, interaction: discord.Interaction, current: str):
        if interaction.guild is None:
            return []
        nomi = await custom_command_repo.nomi_di(interaction.guild.id, interaction.user.id, current.lower(), 25)
        return [app_commands.Choice(name=n, value=n) for n in nomi]

    @autocomplete_protetto(Livello.ADMIN)
    async def _tutti(self, interaction: discord.Interaction, current: str):
        if interaction.guild is None:
            return []
        return [app_commands.Choice(name=n, value=n) for n in await custom_command_repo.search_names(interaction.guild.id, current.lower(), 25)]

    # ------------------------------------------------------------ i tag di chi li ha creati
    async def _puo_creare(self, interaction: discord.Interaction) -> bool:
        ruolo_id = await db.get_guild_setting(interaction.guild.id, SETTING_RUOLO_CREATORI)
        return bool(ruolo_id) and any(r.id == ruolo_id for r in interaction.user.roles)

    @comando_di_gruppo("tag", nome="crea", descrizione="Crea un tag tuo (serve il ruolo scelto dal server).")
    @app_commands.describe(nome="Il nome (lettere minuscole, cifre, - e _)", testo="Cosa risponde il tag")
    async def crea(self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, MAX_NOME],
                   testo: app_commands.Range[str, 1, MAX_TESTO_PUBBLICO]) -> None:
        if not await self._pronto(interaction):
            return
        if not await self._puo_creare(interaction):
            await self._dire(interaction, "tag_non_puoi_creare")
            return
        normalizzato = normalizza_nome(nome)
        if normalizzato is None:
            await self._dire(interaction, "forms_il_nome_puo_avere_solo")
            return
        if await custom_command_repo.conta_di(interaction.guild.id, interaction.user.id) >= MAX_TAG_PER_CREATORE:
            await self._dire(interaction, "tag_troppi_tuoi", massimo=MAX_TAG_PER_CREATORE)
            return
        esito = await custom_command_repo.create_tag(
            interaction.guild.id, normalizzato, response=discord.utils.escape_mentions(testo), use_embed=False, role_id=None, role_action="nessuna",
            cooldown_seconds=5, ping_ruoli=False, created_by=interaction.user.id)  # niente ruoli: chi crea non è staff
        await self._dire(interaction, {"ok": "tag_creato", "esiste": "tag_esiste_gia", "pieno": "tag_server_pieno"}[esito], nome=normalizzato, massimo=MAX_TAG)

    @comando_di_gruppo("tag", nome="modifica", descrizione="Cambia il testo di un tag che hai creato tu.")
    @app_commands.describe(nome="Il tuo tag", testo="Il nuovo testo")
    @app_commands.autocomplete(nome=_miei)
    async def modifica(self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, MAX_NOME],
                       testo: app_commands.Range[str, 1, MAX_TESTO_PUBBLICO]) -> None:
        if not await self._pronto(interaction):
            return
        normalizzato = normalizza_nome(nome)
        tag = await custom_command_repo.get_tag(interaction.guild.id, normalizzato) if normalizzato else None
        if tag is None or tag.created_by != interaction.user.id:
            await self._dire(interaction, "tag_non_tuo")
            return
        await custom_command_repo.update_tag(interaction.guild.id, normalizzato, response=discord.utils.escape_mentions(testo))
        await self._dire(interaction, "tag_modificato")

    @comando_di_gruppo("tag", nome="elimina", descrizione="Elimina un tag che hai creato tu.")
    @app_commands.describe(nome="Il tuo tag")
    @app_commands.autocomplete(nome=_miei)
    async def elimina(self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, MAX_NOME]) -> None:
        if not await self._pronto(interaction):
            return
        normalizzato = normalizza_nome(nome)
        fatta = bool(normalizzato) and await custom_command_repo.delete_tag_di(interaction.guild.id, normalizzato, interaction.user.id)
        if fatta:
            await tag_inneschi_repo.togli_per_tag(interaction.guild.id, normalizzato)
        await self._dire(interaction, "tag_eliminato" if fatta else "tag_non_tuo")

    @comando_di_gruppo("tag", nome="prendi", descrizione="Prendi un tag il cui autore ha lasciato il server.")
    @app_commands.describe(nome="Il tag")
    async def prendi(self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, MAX_NOME]) -> None:
        if not await self._pronto(interaction):
            return
        normalizzato = normalizza_nome(nome)
        if normalizzato is None or not await self._puo_creare(interaction):
            await self._dire(interaction, "tag_non_puoi_creare")
            return
        guild = interaction.guild
        esito = await custom_command_repo.prendi(guild.id, normalizzato, interaction.user.id, lambda uid: guild.get_member(uid) is not None)
        await self._dire(interaction, {"ok": "tag_preso", "non_esiste": "tag_non_esiste", "tuo": "tag_gia_tuo", "autore_presente": "tag_autore_presente"}[esito])

    # ------------------------------------------------------------ staff
    @comando_di_gruppo("admin-tag", nome="creatori", descrizione="Scegli il ruolo di chi può creare tag propri con /tag crea.", sottogruppo=SOTTOGRUPPI["admin-tag tag"])
    @app_commands.describe(ruolo="Il ruolo (vuoto: nessuno, solo lo staff crea tag)")
    async def creatori(self, interaction: discord.Interaction, ruolo: discord.Role | None = None) -> None:
        if not await self._pronto(interaction):
            return
        if ruolo is not None and (ruolo.is_default() or ruolo.permissions.administrator or ruolo.managed):
            await self._dire(interaction, "tag_ruolo_non_adatto")
            return
        # punto unico (D16): stessi controlli dello schema e stesso storico del pannello web
        await imposta_impostazione(interaction.guild, MODULE_CUSTOM_COMMANDS, SETTING_RUOLO_CREATORI, str(ruolo.id) if ruolo else "", interaction.user.id)
        await self._dire(interaction, "tag_creatori_impostato" if ruolo else "tag_creatori_tolto")

    @comando_di_gruppo("admin-tag", nome="sostituisci", descrizione="Cambia un testo in tutti i tag, dopo l'anteprima.", sottogruppo=SOTTOGRUPPI["admin-tag tag"])
    @app_commands.describe(da="Il testo da cercare (maiuscole contano)", a="Il testo nuovo (vuoto: lo toglie)")
    async def sostituisci(self, interaction: discord.Interaction, da: app_commands.Range[str, 1, 200], a: app_commands.Range[str, 0, 200] = "") -> None:
        if not await self._pronto(interaction):
            return
        quanti = await custom_command_repo.sostituisci(interaction.guild.id, da, a, False)
        if quanti == 0:
            await self._dire(interaction, "tag_sostituisci_nessuno")
            return
        etichette = (await testo_per(interaction, "conteggio_togli_bottone"), await testo_per(interaction, "conteggio_togli_annulla"))
        await interaction.response.send_message(
            await testo_per(interaction, "tag_sostituisci_chiedi", quanti=quanti, da=da[:100], a=a[:100]), ephemeral=True,
            allowed_mentions=_NESSUNA_MENZIONE, view=ConfermaSostituisci(interaction.user.id, interaction.guild.id, da, a, etichette))

    @comando_di_gruppo("admin-tag", nome="esporta", descrizione="Esporta i tag del server in un codice o in un file.", sottogruppo=SOTTOGRUPPI["admin-tag tag"])
    @app_commands.describe(formato="Un codice da dare a chi importa, o un file JSON")
    @app_commands.choices(formato=_SCELTE_FORMATO)
    async def esporta(self, interaction: discord.Interaction, formato: app_commands.Choice[str]) -> None:
        if not await self._pronto(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        tags, risposte = await custom_command_repo.tutti_con_risposte(interaction.guild.id)
        if not tags:
            await interaction.followup.send(await testo_per(interaction, "tag_nessun_tag"), ephemeral=True)
            return
        dati = pacchetto_da_tag(tags, risposte)
        if formato.value == "file":
            await interaction.followup.send(await testo_per(interaction, "tag_esportati_file", quanti=len(tags)), ephemeral=True,
                                            file=discord.File(io.BytesIO(pacchetto_in_file(dati)), filename="tag.json"))
            return
        codice = nuovo_codice()
        await custom_command_repo.crea_pacchetto(interaction.guild.id, dati, interaction.user.id, codice)
        await interaction.followup.send(await testo_per(interaction, "tag_esportati_codice", quanti=len(tags), codice=codice), ephemeral=True)

    @comando_di_gruppo("admin-tag", nome="importa", descrizione="Importa tag da un codice o da un file JSON.", sottogruppo=SOTTOGRUPPI["admin-tag tag"])
    @app_commands.describe(codice="Il codice dato da /admin-tag tag esporta", file="Oppure un file JSON esportato (1 MiB)")
    async def importa(self, interaction: discord.Interaction, codice: app_commands.Range[str, 6, 16] | None = None, file: discord.Attachment | None = None) -> None:
        if not await self._pronto(interaction):
            return
        if (codice is None) == (file is None) or (file is not None and file.size > MAX_BYTE_PACCHETTO):
            await self._dire(interaction, "tag_importa_una_fonte")
            return
        await interaction.response.defer(ephemeral=True)
        try:
            grezzo = await file.read() if file is not None else await custom_command_repo.leggi_pacchetto(codice)
            if grezzo is None:
                await interaction.followup.send(await testo_per(interaction, "tag_codice_scaduto"), ephemeral=True)
                return
            voci = leggi_pacchetto(grezzo)
        except PacchettoErrato as errore:
            await interaction.followup.send(await testo_per(interaction, str(errore)), ephemeral=True)
            return
        aggiunti, saltati = await custom_command_repo.importa(interaction.guild.id, voci, interaction.user.id)
        await interaction.followup.send(await testo_per(interaction, "tag_importati", aggiunti=aggiunti, saltati=saltati), ephemeral=True)

    @comando_di_gruppo("admin-tag", nome="gruppi", descrizione="Regole per gruppo di tag: un solo canale e/o un ruolo richiesto.", sottogruppo=SOTTOGRUPPI["admin-tag tag"])
    @app_commands.describe(azione="Cosa fare", gruppo="Il nome del gruppo (lo dai ai tag con /admin-tag tag opzioni)",
                           canale="I tag del gruppo si usano solo qui", ruolo="I tag del gruppo si usano solo con questo ruolo")
    @app_commands.choices(azione=_SCELTE_GRUPPO)
    async def gruppi(self, interaction: discord.Interaction, azione: app_commands.Choice[str], gruppo: app_commands.Range[str, 1, 32] | None = None,
                     canale: discord.TextChannel | None = None, ruolo: discord.Role | None = None) -> None:
        if not await self._pronto(interaction):
            return
        guild_id = interaction.guild.id
        if azione.value == "elenco":
            righe = [f"`{g['gruppo']}` · {g['tag']} tag" + (f" · <#{g['canale_id']}>" if g["canale_id"] else "") + (f" · <@&{g['ruolo_id']}>" if g["ruolo_id"] else "")
                     for g in await custom_command_repo.elenco_gruppi(guild_id)]
            await interaction.response.send_message("\n".join(righe)[:1900] or await testo_per(interaction, "tag_nessun_gruppo"), ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE)
            return
        nome = nome_gruppo_valido(gruppo or "")
        if nome is None:
            await self._dire(interaction, "tag_gruppo_nome")
            return
        if azione.value == "togli":
            await self._dire(interaction, "tag_gruppo_tolto" if await custom_command_repo.togli_gruppo(guild_id, nome) else "tag_gruppo_inesistente")
            return
        await custom_command_repo.imposta_gruppo(guild_id, nome, canale.id if canale else None, ruolo.id if ruolo else None)
        await self._dire(interaction, "tag_gruppo_salvato", gruppo=nome)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TagGestioneCog(bot))
