"""
cogs/utility/ruoli_extra.py
===========================
Funzioni in più dei ruoli: ruoli in più e gruppi di menu, immagine nel menu, tavolozza dei colori e `/utility identita colore`,
creazione guidata a passi, ruolo personale del membro e immagini proprie del benvenuto.
La logica sta in core/ruoli_extra_logic.py, core/ruoli_guidata_logic.py e core/repositories/ruoli_extra_repo.py.
Funzioni coperte: SPEC RUO-012, RUO-045, RUO-046, RUO-047, RUO-053, RUO-069, RUO-083
Dipende da: cogs/utility/role_menus.py (assegnazione dei ruoli e pubblicazione dei menu)
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.moderation_shadowban import add_roles_se_libero
from core.command_groups import CogConGruppi, SOTTOGRUPPI, comando_di_gruppo
from core.i18n import lingua_interazione, t, testo_per
from core.repositories.role_menu_repo import role_menu_repo
from core.repositories.ruoli_extra_repo import RuoliExtraRepository
from core.role_menu_logic import EMOJI_PREDEFINITE, Decisione, membro_ammesso
from core.role_safety import check_role_assignable
from core.ruoli_extra_logic import (
    MAX_IMMAGINI_BENVENUTO,
    PAUSA_MODIFICHE_SECONDI,
    posizione_sotto_il_bot,
    puo_aggiungere_extra,
    puo_creare_ruolo_personale,
    pulisci_nome_gruppo,
    pulisci_nome_ruolo,
    secondi_di_pausa,
    valida_colore,
)
from core.ruoli_guidata_logic import (
    MODALITA,
    TEMPO_MASSIMO_SECONDI,
    StatoGuidato,
    coppie_in_testo,
    emoji_da_testo,
)
from core.ruoli_immagini import ricodifica_per_menu
from core.safe_http import safe_richiesta_byte, url_e_sicuro
from core.safe_image import MAX_IMAGE_BYTES, ImmagineTroppoGrande, run_image_task
from core.ui_base import BaseModal, BaseView

logger = logging.getLogger("iyokai.ruoli_extra")

NESSUNA_MENZIONE = discord.AllowedMentions.none()
MAX_INDIRIZZO = 500


def _repo() -> RuoliExtraRepository:
    return RuoliExtraRepository(role_menu_repo.pool_provider())


async def _menu_del_server(interaction: discord.Interaction, menu_id: int):
    """Il menu, se è di questo server; altrimenti risponde e torna None."""
    menu = await role_menu_repo.get_menu(menu_id)
    if interaction.guild is None or menu is None or menu.guild_id != interaction.guild.id:
        await interaction.response.send_message(await testo_per(interaction, "ruoli_extra_menu_non_trovato"), ephemeral=True)
        return None
    return menu


# ======================================================================
# RUO-047: creazione guidata
# ======================================================================
class TestoMenuModal(BaseModal, title="Titolo e descrizione del menu"):
    titolo = discord.ui.TextInput(label="Titolo", max_length=256)
    descrizione = discord.ui.TextInput(label="Descrizione (facoltativa)", style=discord.TextStyle.paragraph, required=False, max_length=2000)

    def __init__(self, vista: "CreazioneGuidata") -> None:
        super().__init__(timeout=TEMPO_MASSIMO_SECONDI)
        self.vista = vista

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not await self.vista.autorizza(interaction):
            return
        self.vista.stato.titolo = str(self.titolo).strip()[:256] or "Ruoli"
        self.vista.stato.descrizione = str(self.descrizione).strip()[:2000]
        await self.vista.avanti(interaction)


class EmojiMenuModal(BaseModal, title="Emoji dei ruoli"):
    emoji = discord.ui.TextInput(label="Un'emoji per riga, come i ruoli", style=discord.TextStyle.paragraph, required=False, max_length=1000)

    def __init__(self, vista: "CreazioneGuidata") -> None:
        super().__init__(timeout=TEMPO_MASSIMO_SECONDI)
        self.vista = vista

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not await self.vista.autorizza(interaction):
            return
        s = self.vista.stato
        emoji, errore = emoji_da_testo(str(self.emoji), len(s.ruoli), obbligatorie=s.modalita == "reaction")
        if errore is not None:
            await interaction.response.send_message(errore, ephemeral=True)
            return
        s.emoji, s.emoji_fatte = emoji, True
        await self.vista.avanti(interaction)


class CreazioneGuidata(BaseView):
    """
    I passi stanno in questa View, legata a chi l'ha avviata (e che deve ancora poter gestire il server),
    e si chiude da sola dopo TEMPO_MASSIMO_SECONDI.
    """

    def __init__(self, cog: "RuoliExtraCog", autore: discord.Member, lingua: str) -> None:
        super().__init__(timeout=TEMPO_MASSIMO_SECONDI)
        self.cog = cog
        self.stato = StatoGuidato(autore_id=autore.id)
        self.lingua = lingua
        self.interazione_iniziale: discord.Interaction | None = None
        self.concluso = False

    async def autorizza(self, interaction: discord.Interaction) -> bool:
        """Solo chi ha avviato la procedura, e solo se può ancora gestire il server (si ricontrolla a ogni passo)."""
        utente = interaction.user
        ok = (
            utente.id == self.stato.autore_id
            and isinstance(utente, discord.Member)
            and utente.guild_permissions.manage_guild
        )
        if not ok:
            await interaction.response.send_message(t("ruoli_extra_wiz_non_tuo", self.lingua), ephemeral=True)
        return ok

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        return await self.autorizza(interaction)

    def _testo_passo(self) -> str:
        return t(f"ruoli_extra_wiz_passo_{self.stato.passo()}", self.lingua)

    def disegna(self) -> None:
        self.clear_items()
        passo = self.stato.passo()
        if passo == "modalita":
            scelta = discord.ui.Select(
                placeholder=t("ruoli_extra_wiz_modalita", self.lingua),
                options=[discord.SelectOption(label=t(f"ruoli_extra_wiz_m_{m}", self.lingua), value=m) for m in MODALITA],
            )
            scelta.callback = self._dopo_modalita(scelta)
            self.add_item(scelta)
        elif passo == "testo":
            bottone = discord.ui.Button(label=t("ruoli_extra_wiz_scrivi", self.lingua), style=discord.ButtonStyle.primary)
            bottone.callback = self._apri_modale(TestoMenuModal)
            self.add_item(bottone)
        elif passo == "canale":
            canali = discord.ui.ChannelSelect(channel_types=[discord.ChannelType.text], min_values=1, max_values=1)
            canali.callback = self._dopo_canale(canali)
            self.add_item(canali)
        elif passo == "ruoli":
            ruoli = discord.ui.RoleSelect(min_values=1, max_values=25)
            ruoli.callback = self._dopo_ruoli(ruoli)
            self.add_item(ruoli)
        elif passo == "emoji":
            bottone = discord.ui.Button(label=t("ruoli_extra_wiz_emoji", self.lingua), style=discord.ButtonStyle.primary)
            bottone.callback = self._apri_modale(EmojiMenuModal)
            self.add_item(bottone)
            if self.stato.modalita != "reaction":
                salta = discord.ui.Button(label=t("ruoli_extra_wiz_senza_emoji", self.lingua))
                salta.callback = self._senza_emoji
                self.add_item(salta)
        else:
            ok = discord.ui.Button(label=t("ruoli_extra_wiz_crea", self.lingua), style=discord.ButtonStyle.success)
            ok.callback = self._crea
            self.add_item(ok)
        annulla = discord.ui.Button(label=t("ruoli_extra_wiz_annulla", self.lingua), style=discord.ButtonStyle.danger)
        annulla.callback = self._annulla
        self.add_item(annulla)

    async def avanti(self, interaction: discord.Interaction) -> None:
        self.disegna()
        await interaction.response.edit_message(content=self._testo_passo(), view=self)

    def _dopo_modalita(self, scelta: discord.ui.Select):
        async def callback(interaction: discord.Interaction) -> None:
            if scelta.values[0] in MODALITA:
                self.stato.modalita = scelta.values[0]
            await self.avanti(interaction)
        return callback

    def _apri_modale(self, classe):
        async def callback(interaction: discord.Interaction) -> None:
            await interaction.response.send_modal(classe(self))
        return callback

    def _dopo_canale(self, canali: discord.ui.ChannelSelect):
        async def callback(interaction: discord.Interaction) -> None:
            self.stato.canale_id = canali.values[0].id
            await self.avanti(interaction)
        return callback

    def _dopo_ruoli(self, scelti: discord.ui.RoleSelect):
        async def callback(interaction: discord.Interaction) -> None:
            self.stato.ruoli = [r.id for r in scelti.values]
            self.stato.emoji, self.stato.emoji_fatte = [], False
            await self.avanti(interaction)
        return callback

    async def _senza_emoji(self, interaction: discord.Interaction) -> None:
        self.stato.emoji, self.stato.emoji_fatte = [None] * len(self.stato.ruoli), True
        await self.avanti(interaction)

    async def _annulla(self, interaction: discord.Interaction) -> None:
        self.concluso = True
        self.stop()
        await interaction.response.edit_message(content=t("ruoli_extra_wiz_annullata", self.lingua), view=None)

    async def _crea(self, interaction: discord.Interaction) -> None:
        guild, s = interaction.guild, self.stato
        await interaction.response.defer()
        self.concluso = True
        self.stop()
        esito = await self.cog.crea_menu_guidato(guild, interaction.user, s)
        await interaction.edit_original_response(content=esito, view=None)

    async def on_timeout(self) -> None:
        if self.concluso or self.interazione_iniziale is None:
            return
        try:
            await self.interazione_iniziale.edit_original_response(content=t("ruoli_extra_wiz_scaduta", self.lingua), view=None)
        except discord.HTTPException:
            pass


# ======================================================================
# Autocompletamenti
# ======================================================================
async def _completa_colori(interaction: discord.Interaction, scritto: str) -> list[app_commands.Choice[str]]:
    """RUO-046: al massimo 25 colori della tavolozza che contengono il testo scritto."""
    if interaction.guild is None:
        return []
    voci = await _repo().ruoli_colore(interaction.guild.id)
    parola = scritto.lower().strip()
    scelte = []
    for rid, etichetta, _, _ in voci:
        ruolo = interaction.guild.get_role(rid)
        nome = (etichetta or (ruolo.name if ruolo else ""))[:90]
        if ruolo is None or (parola and parola not in nome.lower()):
            continue
        scelte.append(app_commands.Choice(name=nome or str(rid), value=str(rid)))
        if len(scelte) == 25:
            break
    return scelte


class RuoliExtraCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _cog_menu(self):
        return self.bot.get_cog("RoleMenuCog")

    # ------------------------------------------------------------ RUO-083
    @comando_di_gruppo(
        "admin-ruoli-menu",
        nome="ruoli-extra",
        descrizione="Una opzione di un menu dà anche altri ruoli (al massimo 5 in tutto).",
    )
    @app_commands.describe(menu_id="ID del menu", ruolo="Il ruolo dell'opzione", extra="Il ruolo in più", togli="Togli il ruolo in più invece di aggiungerlo")
    async def ruoli_extra(
        self, interaction: discord.Interaction, menu_id: int, ruolo: discord.Role, extra: discord.Role, togli: bool = False
    ) -> None:
        menu = await _menu_del_server(interaction, menu_id)
        if menu is None or not isinstance(interaction.user, discord.Member):
            return
        guild, repo = interaction.guild, _repo()
        if ruolo.id not in {o.role_id for o in await role_menu_repo.get_options(menu_id)}:
            await interaction.response.send_message(await testo_per(interaction, "ruoli_extra_opzione_non_trovata"), ephemeral=True)
            return
        if togli:
            ok = await repo.togli_extra(menu_id, ruolo.id, extra.id)
            chiave = "ruoli_extra_extra_tolto" if ok else "ruoli_extra_extra_non_c_era"
        else:
            if extra.id == ruolo.id:
                await interaction.response.send_message(await testo_per(interaction, "ruoli_extra_stesso_ruolo"), ephemeral=True)
                return
            rifiuto = check_role_assignable(guild, extra, interaction.user, self_service=True)
            if rifiuto is None:
                attuali = (await repo.extra_del_menu(menu_id)).get(ruolo.id, ())
                rifiuto = puo_aggiungere_extra(len(attuali), extra.id in attuali)
            if rifiuto is not None:
                await interaction.response.send_message(rifiuto, ephemeral=True)
                return
            await repo.aggiungi_extra(menu_id, ruolo.id, extra.id)
            chiave = "ruoli_extra_extra_aggiunto"
        await interaction.response.send_message(
            await testo_per(interaction, chiave, ruolo=ruolo.name[:60], extra=extra.name[:60]), ephemeral=True, allowed_mentions=NESSUNA_MENZIONE
        )

    # ------------------------------------------------------------ RUO-069
    @comando_di_gruppo(
        "admin-ruoli-menu",
        nome="gruppo",
        descrizione="Collega più menu: tra tutti si tiene un solo ruolo. Nome vuoto: scollega.",
    )
    @app_commands.describe(menu_id="ID del menu", nome="Nome del gruppo (vuoto: il menu esce dal gruppo)")
    async def gruppo(self, interaction: discord.Interaction, menu_id: int, nome: app_commands.Range[str, 0, 40] = "") -> None:
        menu = await _menu_del_server(interaction, menu_id)
        if menu is None:
            return
        pulito = pulisci_nome_gruppo(nome) if nome.strip() else None
        if nome.strip() and pulito is None:
            await interaction.response.send_message(await testo_per(interaction, "ruoli_extra_gruppo_nome_non_valido"), ephemeral=True)
            return
        rifiuto = await _repo().imposta_gruppo(menu_id, interaction.guild.id, pulito)
        if rifiuto is not None:
            await interaction.response.send_message(rifiuto, ephemeral=True)
            return
        chiave = "ruoli_extra_gruppo_impostato" if pulito else "ruoli_extra_gruppo_tolto"
        await interaction.response.send_message(
            await testo_per(interaction, chiave, id=menu_id, nome=pulito or ""), ephemeral=True, allowed_mentions=NESSUNA_MENZIONE
        )

    # ------------------------------------------------------------ RUO-053
    @comando_di_gruppo(
        "admin-ruoli-menu",
        nome="immagine",
        descrizione="Metti un'immagine dentro il messaggio del menu (allegato o indirizzo).",
    )
    @app_commands.describe(
        menu_id="ID del menu", allegato="L'immagine da mettere", indirizzo="Oppure l'indirizzo di un'immagine", togli="Togli l'immagine"
    )
    async def immagine(
        self,
        interaction: discord.Interaction,
        menu_id: int,
        allegato: discord.Attachment | None = None,
        indirizzo: app_commands.Range[str, 0, MAX_INDIRIZZO] = "",
        togli: bool = False,
    ) -> None:
        menu = await _menu_del_server(interaction, menu_id)
        if menu is None:
            return
        if menu.external:
            await interaction.response.send_message(await testo_per(interaction, "ruoli_extra_img_menu_esterno"), ephemeral=True)
            return
        repo = _repo()
        if togli:
            await repo.togli_immagine_menu(menu_id)
            chiave = "ruoli_extra_img_tolta"
        else:
            if (allegato is None) == (not indirizzo.strip()):
                await interaction.response.send_message(await testo_per(interaction, "ruoli_extra_img_una_fonte"), ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True)
            dati = await self._scarica(allegato, indirizzo.strip())
            if dati is None:
                await interaction.followup.send(await testo_per(interaction, "ruoli_extra_img_non_valida"), ephemeral=True)
                return
            try:
                copia = await run_image_task(ricodifica_per_menu, dati)
            except (ImmagineTroppoGrande, OSError, ValueError):  # UnidentifiedImageError è un OSError
                await interaction.followup.send(await testo_per(interaction, "ruoli_extra_img_non_valida"), ephemeral=True)
                return
            await repo.imposta_immagine_menu(menu_id, copia)
            chiave = "ruoli_extra_img_ok"
        cog = self._cog_menu()
        if cog is not None and menu.message_id is not None and not menu.external:
            async with cog._blocco_menu(menu_id):
                try:
                    await cog._pubblica_menu(interaction.guild, menu, await role_menu_repo.get_options(menu_id))
                except Exception as errore:  # MenuNonPubblicabile o altro: l'immagine è salvata, il messaggio si aggiorna alla prossima modifica
                    logger.info("Messaggio del menu %s non aggiornato con l'immagine: %s", menu_id, errore)
        testo = await testo_per(interaction, chiave)
        if interaction.response.is_done():
            await interaction.followup.send(testo, ephemeral=True)
        else:
            await interaction.response.send_message(testo, ephemeral=True)

    @staticmethod
    async def _scarica(allegato: discord.Attachment | None, indirizzo: str) -> bytes | None:
        """I byte dell'immagine: dall'allegato (con il tetto di peso) o dall'indirizzo (safe_http); mai altrove."""
        if allegato is not None:
            if allegato.size > MAX_IMAGE_BYTES:
                return None
            try:
                return await allegato.read()
            except discord.HTTPException:
                return None
        if not await url_e_sicuro(indirizzo):
            return None
        scaricata = await safe_richiesta_byte(indirizzo, max_bytes=MAX_IMAGE_BYTES)
        return scaricata[0] if scaricata else None

    # ------------------------------------------------------------ RUO-046
    @comando_di_gruppo(
        "admin-ruoli-menu",
        nome="colori",
        descrizione="Usa i ruoli di un menu «unique» come tavolozza dei colori del nome.",
    )
    @app_commands.describe(menu_id="ID del menu (comportamento unique)", attivo="Sì: è la tavolozza; no: non lo è più")
    async def colori(self, interaction: discord.Interaction, menu_id: int, attivo: bool = True) -> None:
        menu = await _menu_del_server(interaction, menu_id)
        if menu is None:
            return
        if attivo and menu.behavior != "unique":
            await interaction.response.send_message(await testo_per(interaction, "ruoli_extra_colori_serve_unique"), ephemeral=True)
            return
        await _repo().imposta_colori(menu_id, interaction.guild.id, attivo)
        chiave = "ruoli_extra_colori_on" if attivo else "ruoli_extra_colori_off"
        await interaction.response.send_message(await testo_per(interaction, chiave, id=menu_id), ephemeral=True)

    @comando_di_gruppo(
        "utility", nome="colore", descrizione="Scegli il colore del tuo nome dalla tavolozza del server.",
        sottogruppo=SOTTOGRUPPI["utility identita"],
    )
    @app_commands.describe(colore="Un colore della tavolozza", togli="Togli il tuo colore")
    @app_commands.autocomplete(colore=_completa_colori)
    async def colore(self, interaction: discord.Interaction, colore: app_commands.Range[str, 0, 30] = "", togli: bool = False) -> None:
        guild, utente = interaction.guild, interaction.user
        if guild is None or not isinstance(utente, discord.Member):
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return
        voci = await _repo().ruoli_colore(guild.id)
        if not voci:
            await interaction.response.send_message(await testo_per(interaction, "ruoli_extra_colore_nessuno"), ephemeral=True)
            return
        tavolozza = {rid for rid, *_ in voci}
        scelto = next((v for v in voci if str(v[0]) == colore), None)
        if not togli and scelto is None:
            await interaction.response.send_message(await testo_per(interaction, "ruoli_extra_colore_non_in_tavolozza"), ephemeral=True)
            return
        cog = self._cog_menu()
        if cog is None:
            await interaction.response.send_message(await testo_per(interaction, "ruoli_extra_non_disponibile"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        menu_blocco = next((v for v in voci if scelto and v[0] == scelto[0]), None)
        async with cog._blocco_membro(-1, utente.id):  # un solo cambio di colore alla volta per persona
            membro = await cog._membro_aggiornato(guild, utente)
            ruoli_membro = {r.id for r in membro.roles}
            if not togli:
                negato = membro_ammesso(list(menu_blocco[2]), list(menu_blocco[3]), ruoli_membro)
                if negato is not None:
                    await interaction.followup.send(negato, ephemeral=True)
                    return
            vecchi = tuple(sorted((tavolozza & ruoli_membro) - ({scelto[0]} if scelto and not togli else set())))
            decisione = Decisione(aggiungi=() if togli or scelto[0] in ruoli_membro else (scelto[0],), togli=vecchi)
            errore = await cog._applica(guild, membro, decisione, "Colore del nome", atomico=bool(decisione.aggiungi and vecchi))
        if errore is not None:
            await interaction.followup.send(errore, ephemeral=True)
            return
        ruolo = guild.get_role(scelto[0]) if scelto and not togli else None
        chiave = "ruoli_extra_colore_scelto" if ruolo else "ruoli_extra_colore_tolto"
        await interaction.followup.send(
            await testo_per(interaction, chiave, ruolo=ruolo.name[:60] if ruolo else ""), ephemeral=True, allowed_mentions=NESSUNA_MENZIONE
        )

    # ------------------------------------------------------------ RUO-047
    @comando_di_gruppo(
        "admin-ruoli-menu",
        nome="guidata",
        descrizione="Crea un menu dei ruoli a passi: tipo, testo, canale, ruoli ed emoji.",
    )
    async def guidata(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return
        vista = CreazioneGuidata(self, interaction.user, await lingua_interazione(interaction))
        vista.disegna()
        await interaction.response.send_message(vista._testo_passo(), view=vista, ephemeral=True)
        vista.interazione_iniziale = interaction

    async def crea_menu_guidato(self, guild: discord.Guild, attore: discord.Member, s: StatoGuidato) -> str:
        """Crea il menu con le scelte della procedura. Se i ruoli non passano i controlli il menu non resta."""
        cog = self._cog_menu()
        if cog is None or not attore.guild_permissions.manage_guild:
            return "Non posso creare il menu adesso."
        canale = guild.get_channel(s.canale_id) if s.canale_id else None
        if not isinstance(canale, discord.TextChannel):
            return "Il canale non esiste più."
        menu_id = await role_menu_repo.create_menu(
            guild_id=guild.id, channel_id=canale.id, mode=s.modalita, toggle=True,
            max_selectable=None, title=s.titolo or "Ruoli", description=s.descrizione,
        )
        esito = await cog._aggiungi_coppie(
            guild, attore, menu_id, coppie_in_testo(s.ruoli, s.emoji),
            predefinite=EMOJI_PREDEFINITE if s.modalita == "button" else (),  # i bottoni senza emoji ne ricevono una pronta
        )
        if not esito.startswith("Aggiunte"):
            await role_menu_repo.delete_menu(menu_id)
            return esito
        return f"Menu creato (ID {menu_id}) in {canale.mention}. {esito}"

    # ------------------------------------------------------------ RUO-045
    @comando_di_gruppo(
        "admin-ruoli-menu",
        nome="personale",
        descrizione="Concedi o togli a un membro il ruolo personale (nome e colore scelti da lui).",
    )
    @app_commands.describe(membro="Il membro", togli="Togli il permesso e cancella il suo ruolo personale")
    async def personale(self, interaction: discord.Interaction, membro: discord.Member, togli: bool = False) -> None:
        guild = interaction.guild
        if guild is None or membro.bot:
            await interaction.response.send_message(await testo_per(interaction, "ruoli_extra_pers_non_valido"), ephemeral=True)
            return
        repo = _repo()
        if togli:
            ruolo_id = await repo.revoca_ruolo_personale(guild.id, membro.id)
            await self._cancella_ruolo(guild, ruolo_id, "Ruolo personale revocato")
            chiave = "ruoli_extra_pers_revocato"
        else:
            rifiuto = await repo.concedi_ruolo_personale(guild.id, membro.id, interaction.user.id)
            if rifiuto is not None:
                await interaction.response.send_message(rifiuto, ephemeral=True)
                return
            chiave = "ruoli_extra_pers_concesso"
        await interaction.response.send_message(
            await testo_per(interaction, chiave, membro=membro.display_name[:60]), ephemeral=True, allowed_mentions=NESSUNA_MENZIONE
        )

    @staticmethod
    async def _cancella_ruolo(guild: discord.Guild, ruolo_id: int | None, motivo: str) -> None:
        ruolo = guild.get_role(ruolo_id) if ruolo_id else None
        if ruolo is None or ruolo.managed or ruolo.is_default():
            return
        try:
            await ruolo.delete(reason=motivo)
        except discord.HTTPException:
            logger.info("Ruolo personale %s non cancellato nel server %s.", ruolo_id, guild.id)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Chi lascia il server perde il permesso e il ruolo personale (non resta un ruolo senza padrone)."""
        try:
            ruolo_id = await _repo().revoca_ruolo_personale(member.guild.id, member.id)
        except Exception:
            logger.exception("Ruolo personale non ripulito (server %s).", member.guild.id)
            return
        await self._cancella_ruolo(member.guild, ruolo_id, "Il membro ha lasciato il server")

    @comando_di_gruppo(
        "utility",
        nome="ruolo-mio",
        descrizione="Cambia nome e colore del tuo ruolo personale (se lo staff te l'ha concesso).",
        sottogruppo=SOTTOGRUPPI["utility identita"],
    )
    @app_commands.describe(nome="Il nome del ruolo (massimo 100 caratteri)", colore="Il colore, per esempio #C24A3A", elimina="Cancella il tuo ruolo")
    async def ruolo_mio(
        self,
        interaction: discord.Interaction,
        nome: app_commands.Range[str, 0, 100] = "",
        colore: app_commands.Range[str, 0, 7] = "",
        elimina: bool = False,
    ) -> None:
        guild, utente = interaction.guild, interaction.user
        if guild is None or not isinstance(utente, discord.Member):
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return
        repo = _repo()
        riga = await repo.ruolo_personale(guild.id, utente.id)
        if riga is None:
            await interaction.response.send_message(await testo_per(interaction, "ruoli_extra_pers_non_concesso"), ephemeral=True)
            return
        if elimina:
            await self._cancella_ruolo(guild, riga["role_id"], "Il membro ha cancellato il suo ruolo")
            await repo.segna_ruolo_personale(guild.id, utente.id, None, discord.utils.utcnow())
            await interaction.response.send_message(await testo_per(interaction, "ruoli_extra_pers_eliminato"), ephemeral=True)
            return
        nome_pulito = pulisci_nome_ruolo(nome) if nome.strip() else None
        if nome.strip() and nome_pulito is None:
            await interaction.response.send_message(await testo_per(interaction, "ruoli_extra_pers_nome_non_valido"), ephemeral=True)
            return
        valore_colore = valida_colore(colore) if colore.strip() else None
        if colore.strip() and valore_colore is None:
            await interaction.response.send_message(await testo_per(interaction, "ruoli_extra_pers_colore_non_valido"), ephemeral=True)
            return
        ruolo = guild.get_role(riga["role_id"]) if riga["role_id"] else None
        if ruolo is None and nome_pulito is None:
            await interaction.response.send_message(await testo_per(interaction, "ruoli_extra_pers_serve_nome"), ephemeral=True)
            return
        if ruolo is None:
            rifiuto = puo_creare_ruolo_personale(await repo.conta_ruoli_personali(guild.id), len(guild.roles))
            if rifiuto is not None:
                await interaction.response.send_message(rifiuto, ephemeral=True)
                return
        # Un solo passaggio alla volta per persona e una pausa tra le modifiche: i ruoli hanno limiti stretti su Discord.
        ora = discord.utils.utcnow()
        if not await repo.prenota_modifica(guild.id, utente.id, ora, PAUSA_MODIFICHE_SECONDI):
            attesa = secondi_di_pausa(riga["ultima_modifica"], ora)
            await interaction.response.send_message(await testo_per(interaction, "ruoli_extra_pers_pausa", secondi=max(attesa, 1)), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        errore = await self._crea_o_aggiorna(guild, utente, ruolo, nome_pulito, valore_colore, ora)
        await interaction.followup.send(
            errore or await testo_per(interaction, "ruoli_extra_pers_fatto"), ephemeral=True, allowed_mentions=NESSUNA_MENZIONE
        )

    async def _crea_o_aggiorna(
        self, guild: discord.Guild, utente: discord.Member, ruolo: discord.Role | None,
        nome: str | None, colore: int | None, ora,
    ) -> str | None:
        """Il ruolo personale ha SEMPRE permessi vuoti, sta sotto il ruolo del bot ed è usato solo dal suo padrone."""
        me = guild.me
        vuoti = discord.Permissions.none()
        try:
            if ruolo is None:
                ruolo = await guild.create_role(
                    name=nome, colour=discord.Colour(colore or 0), permissions=vuoti, hoist=False, mentionable=False,
                    reason="Ruolo personale",
                )
                await ruolo.edit(position=posizione_sotto_il_bot(me.top_role.position), reason="Ruolo personale")
            else:
                if ruolo >= me.top_role or ruolo.managed or ruolo.is_default():
                    return "Non posso modificare quel ruolo: sta sopra il mio."
                campi = {"permissions": vuoti, "reason": "Ruolo personale"}
                if nome is not None:
                    campi["name"] = nome
                if colore is not None:
                    campi["colour"] = discord.Colour(colore)
                await ruolo.edit(**campi)
            rifiuto = check_role_assignable(guild, ruolo, me, self_service=True)
            if rifiuto is not None:
                return rifiuto
            if ruolo not in utente.roles:
                await add_roles_se_libero(utente, ruolo, reason="Ruolo personale")
        except discord.Forbidden:
            return "Non ho il permesso di gestire quel ruolo."
        except discord.HTTPException:
            logger.warning("Ruolo personale non gestito nel server %s.", guild.id)
            return "Discord ha dato un errore: riprova tra poco."
        await _repo().segna_ruolo_personale(guild.id, utente.id, ruolo.id, ora)
        return None

    # ------------------------------------------------------------ RUO-012
    @comando_di_gruppo(
        "admin-benvenuto",
        nome="immagini",
        descrizione="Immagini proprie del benvenuto (al massimo 10): a ogni ingresso se ne sceglie una a caso.",
    )
    @app_commands.describe(
        azione="Aggiungi, togli o mostra l'elenco", allegato="L'immagine da aggiungere", numero="Il numero dell'immagine da togliere"
    )
    @app_commands.choices(azione=[
        app_commands.Choice(name="aggiungi", value="aggiungi"),
        app_commands.Choice(name="togli", value="togli"),
        app_commands.Choice(name="elenco", value="elenco"),
    ])
    async def immagini(
        self,
        interaction: discord.Interaction,
        azione: str,
        allegato: discord.Attachment | None = None,
        numero: app_commands.Range[int, 1, 2_000_000_000] | None = None,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            return
        repo = _repo()
        if azione == "elenco":
            ids = await repo.id_immagini_benvenuto(guild.id)
            testo = await testo_per(interaction, "ruoli_extra_bv_elenco", n=len(ids), max=MAX_IMMAGINI_BENVENUTO, ids=", ".join(map(str, ids)) or "-")
            await interaction.response.send_message(testo, ephemeral=True)
            return
        if azione == "togli":
            ok = numero is not None and await repo.togli_immagine_benvenuto(guild.id, numero)
            await interaction.response.send_message(
                await testo_per(interaction, "ruoli_extra_bv_tolta" if ok else "ruoli_extra_bv_non_trovata"), ephemeral=True
            )
            return
        if allegato is None:
            await interaction.response.send_message(await testo_per(interaction, "ruoli_extra_bv_serve_allegato"), ephemeral=True)
            return
        from core.welcome_image import prepara_sfondo

        await interaction.response.defer(ephemeral=True)
        dati = await self._scarica(allegato, "")
        try:
            copia = await run_image_task(prepara_sfondo, dati) if dati is not None else None
        except (ImmagineTroppoGrande, OSError, ValueError):
            copia = None
        if copia is None:
            await interaction.followup.send(await testo_per(interaction, "ruoli_extra_img_non_valida"), ephemeral=True)
            return
        nuovo = await repo.aggiungi_immagine_benvenuto(guild.id, copia, interaction.user.id)
        if nuovo is None:
            await interaction.followup.send(await testo_per(interaction, "ruoli_extra_bv_piene", max=MAX_IMMAGINI_BENVENUTO), ephemeral=True)
            return
        await interaction.followup.send(await testo_per(interaction, "ruoli_extra_bv_salvata", id=nuovo), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RuoliExtraCog(bot))
