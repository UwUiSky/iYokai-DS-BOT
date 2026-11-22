"""
cogs/moderation/opzioni.py
==========================
Opzioni di moderazione del server (`/mod-sanzioni opzioni`): giorni di messaggi
cancellati al ban, durata predefinita del timeout, DM per tipo di azione,
ruoli immuni alla moderazione manuale, casi per le azioni fatte fuori da
iYokai, avvisi allo staff. La logica e il salvataggio sono in
core/moderation_opzioni.py (un solo punto, anche per il pannello web).
Funzioni coperte: SPEC §5.13 (MOD-010, MOD-017, MOD-018, MOD-019, MOD-057, MOD-060, MOD-068), CFG-024, §5.2 (MOD-047), §5.3 (MOD-036, MOD-064)
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from cogs.moderation._shared import MODULE_ACTIONS, audit_reason, ensure_module_enabled, format_duration, parse_duration
from cogs.moderation.softban_mute import SETTING_MUTE_ROLE_ID, aggiorna_ruolo_muto
from cogs.moderation._shared import SETTING_AVVISO_CANALE
from core import moderation_dm
from core import moderation_aspetto
from core import moderation_permessi_azioni as permessi_azioni
from core import moderation_opzioni as opzioni
from core.command_groups import SOTTOGRUPPI, CogConGruppi, comando_di_gruppo
from core.database import db
from core.i18n import testo_per
from core.role_safety import check_role_assignable
from core.ui_base import BaseModal

SOTTOGRUPPO = ("opzioni", "Opzioni di moderazione del server.")

_NOMI_AZIONI = {
    "warn": "Warn",
    "kick": "Kick",
    "ban": "Ban",
    "tempban": "Tempban",
    "softban": "Softban",
    "timeout": "Timeout",
    "mute": "Mute con ruolo",
}


def _puo_gestire(interaction: discord.Interaction) -> bool:
    permessi = interaction.user.guild_permissions
    return permessi.administrator or permessi.manage_guild


def _riepilogo(guild: discord.Guild, o: opzioni.OpzioniModerazione) -> discord.Embed:
    dm = ", ".join(_NOMI_AZIONI[a] for a in opzioni.AZIONI_CON_DM if a not in o.dm_spenti) or "nessuna"
    immuni = " ".join(f"<@&{r}>" for r in o.ruoli_immuni) or "nessuno"
    embed = discord.Embed(title="Opzioni di moderazione", color=discord.Color.blurple())
    embed.add_field(
        name="Scadenza dei casi AutoMod",
        value=f"{o.scadenza_automod} giorni" if o.scadenza_automod else "mai",
        inline=False,
    )
    embed.add_field(name="Motivo delle sanzioni", value="obbligatorio" if o.motivo_obbligatorio else "facoltativo", inline=False)
    embed.add_field(name="Giorni di messaggi cancellati al ban", value=str(o.giorni_ban), inline=False)
    embed.add_field(
        name="Timeout senza durata",
        value=format_duration(o.durata_timeout) if o.durata_timeout else "durata obbligatoria",
        inline=False,
    )
    embed.add_field(name="DM all'utente per", value=dm[:1024], inline=False)
    embed.add_field(name="Casi visibili a ogni utente", value="sì (/utility mie-sanzioni)" if o.utente_vede_casi else "no", inline=False)
    embed.add_field(name="Conferma prima di sanzionare", value="sì" if o.conferma else "no", inline=False)
    risposta = o.risposte if o.risposte != "cancella-dopo" else f"cancellata dopo {o.risposte_secondi} secondi"
    embed.add_field(name="Risposte dopo una sanzione", value=risposta, inline=False)
    embed.add_field(name="Moderatore nei DM", value="nascosto («Staff di <server>»)" if o.anonimo else "col nome", inline=False)
    if o.dm_testi:
        embed.add_field(name="DM con testo del server", value=", ".join(_NOMI_AZIONI[a] for a in o.dm_testi)[:1024], inline=False)
    embed.add_field(name="Ruoli immuni", value=immuni[:1024], inline=False)
    embed.add_field(
        name="Casi per le azioni fatte fuori da iYokai",
        value="sì (ban, kick, timeout)" if o.casi_esterni else "no",
        inline=False,
    )
    embed.add_field(
        name="Avvisi allo staff",
        value=(
            (f"warn oltre {o.avviso_warn}" if o.avviso_warn else "warn: spento")
            + "; rientro di chi ha casi: " + ("sì" if o.avviso_rientro else "no")
        ),
        inline=False,
    )
    return embed


class ModuloTestoDm(BaseModal):
    """MOD-059: una finestra con un solo campo, il testo del DM di un'azione (fino a 1.500 caratteri)."""

    def __init__(self, azione: str, nome: str, attuale: str | None, titolo: str, campo: str) -> None:
        super().__init__(title=titolo[:45], timeout=600)
        self.azione = azione
        self.nome = nome
        self.testo = discord.ui.TextInput(
            label=campo[:45], style=discord.TextStyle.paragraph, max_length=opzioni.MAX_TESTO_DM, required=False, default=attuale
        )
        self.add_item(self.testo)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not _puo_gestire(interaction):  # i permessi possono cambiare mentre la finestra è aperta
            await interaction.response.send_message(await testo_per(interaction, "opzioni_le_opzioni_le_cambia_chi"), ephemeral=True)
            return
        guild = interaction.guild
        await opzioni.imposta_dm_testo(guild.id, self.azione, self.testo.value, interaction.user.id)
        if not self.testo.value.strip():
            await interaction.response.send_message(await testo_per(interaction, "opzioni_dm_testo_tolto", azione=self.nome), ephemeral=True)
            return
        anteprima = moderation_dm.espandi(
            self.testo.value.strip(), {"server": guild.name, "motivo": "…", "durata": "1 ora", "moderatore": interaction.user.mention}
        )
        corpo = await testo_per(interaction, "opzioni_dm_testo_salvato", azione=self.nome, anteprima=anteprima[:1500])
        aiuto = await testo_per(interaction, "opzioni_dm_testo_aiuto", elenco="{server} {motivo} {durata} {moderatore}")
        await interaction.response.send_message(
            f"{corpo}\n{aiuto}"[:2000], ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
        )


class OpzioniModerazioneCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _controlli(self, interaction: discord.Interaction) -> bool:
        if not await ensure_module_enabled(interaction, MODULE_ACTIONS):
            return False
        if not _puo_gestire(interaction):
            await interaction.response.send_message(
                await testo_per(interaction, "opzioni_le_opzioni_le_cambia_chi"), ephemeral=True
            )
            return False
        return True

    @comando_di_gruppo(
        "mod-sanzioni",
        nome="imposta",
        descrizione="Messaggi al ban, timeout, casi esterni, avvisi. Vuoto: mostra le opzioni.",
        sottogruppo=SOTTOGRUPPO,
    )
    @app_commands.describe(
        giorni_ban="Giorni di messaggi cancellati quando il ban non li dice (0-7)",
        durata_timeout="Durata del timeout quando non la scrivi, es. 10m, 1h; «no» per toglierla",
        casi_esterni="Crea un caso anche per ban, kick e timeout fatti dal menu di Discord o da altri bot",
        avviso_warn="Avvisa lo staff quando chi riceve un warn ne ha già questi (0 = spento)",
        avviso_rientro="Avvisa lo staff quando rientra nel server chi ha dei casi",
        scadenza_automod="Dopo quanti giorni i casi dell'AutoMod non contano più (0 = mai)",
        motivo_obbligatorio="Il motivo delle sanzioni è obbligatorio (sì) o si può omettere (no)",
        anonimo="Nei messaggi privati delle sanzioni scrivi «Staff di <server>» invece del nome del moderatore",
        utente_vede_casi="Ogni utente vede i propri casi con /utility mie-sanzioni",
        conferma="Prima di sanzionare chiede «Conferma» o «Annulla» (solo a chi comanda)",
        risposte="Come risponde il bot dopo una sanzione: normale, compatta o cancellata dopo qualche secondo",
        risposte_secondi="Se cancellata dopo: dopo quanti secondi (5-300)",
    )
    @app_commands.choices(
        risposte=[
            app_commands.Choice(name="Normale", value="normale"),
            app_commands.Choice(name="Compatta (una riga)", value="compatta"),
            app_commands.Choice(name="Cancella dopo qualche secondo", value="cancella-dopo"),
        ]
    )
    async def imposta(
        self,
        interaction: discord.Interaction,
        giorni_ban: app_commands.Range[int, 0, 7] | None = None,
        durata_timeout: app_commands.Range[str, 1, 20] | None = None,
        casi_esterni: bool | None = None,
        avviso_warn: app_commands.Range[int, 0, opzioni.MAX_SOGLIA_WARN] | None = None,
        avviso_rientro: bool | None = None,
        scadenza_automod: app_commands.Range[int, 0, opzioni.MAX_SCADENZA_AUTOMOD] | None = None,
        motivo_obbligatorio: bool | None = None,
        anonimo: bool | None = None,
        utente_vede_casi: bool | None = None,
        conferma: bool | None = None,
        risposte: app_commands.Choice[str] | None = None,
        risposte_secondi: app_commands.Range[int, 5, 300] | None = None,
    ) -> None:
        if not await self._controlli(interaction):
            return
        guild = interaction.guild
        if durata_timeout is not None:
            if durata_timeout.strip().lower() == "no":
                secondi = None
            else:
                try:
                    secondi = parse_duration(durata_timeout)
                except ValueError as exc:
                    await interaction.response.send_message(str(exc), ephemeral=True)
                    return
                if not opzioni.MIN_TIMEOUT <= secondi <= opzioni.MAX_TIMEOUT:
                    await interaction.response.send_message(
                        await testo_per(interaction, "opzioni_la_durata_del_timeout_va"), ephemeral=True
                    )
                    return
            await opzioni.imposta_durata_timeout(guild.id, secondi, interaction.user.id)
        # Si salva solo dopo aver controllato tutto: con un errore non cambia niente.
        if giorni_ban is not None:
            await opzioni.imposta_giorni_ban(guild.id, giorni_ban, interaction.user.id)
        if casi_esterni is not None:
            await opzioni.imposta_casi_esterni(guild.id, casi_esterni, interaction.user.id)
        if avviso_warn is not None:
            await opzioni.imposta_avviso_warn(guild.id, avviso_warn, interaction.user.id)
        if avviso_rientro is not None:
            await opzioni.imposta_avviso_rientro(guild.id, avviso_rientro, interaction.user.id)
        if scadenza_automod is not None:
            await opzioni.imposta_scadenza_automod(guild.id, scadenza_automod, interaction.user.id)
        if motivo_obbligatorio is not None:
            await opzioni.imposta_motivo_obbligatorio(guild.id, motivo_obbligatorio, interaction.user.id)
        if anonimo is not None:
            await opzioni.imposta_anonimo(guild.id, anonimo, interaction.user.id)
        if utente_vede_casi is not None:
            await opzioni.imposta_utente_vede_casi(guild.id, utente_vede_casi, interaction.user.id)
        if conferma is not None:
            await opzioni.imposta_conferma(guild.id, conferma, interaction.user.id)
        if risposte is not None or risposte_secondi is not None:
            modo = risposte.value if risposte is not None else (await opzioni.leggi(guild.id)).risposte
            await opzioni.imposta_risposte(guild.id, modo, risposte_secondi, interaction.user.id)
        await interaction.response.send_message(
            embed=_riepilogo(guild, await opzioni.leggi(guild.id)),
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @comando_di_gruppo(
        "mod-sanzioni",
        nome="dm",
        descrizione="Sceglie se l'utente riceve un DM per un tipo di azione.",
        sottogruppo=SOTTOGRUPPO,
    )
    @app_commands.describe(
        azione="Il tipo di azione",
        attivo="Mandare il DM?",
        testo="Sì: apre una finestra per scrivere il testo del DM di questa azione (vuoto: messaggio di base)",
    )
    @app_commands.choices(
        azione=[app_commands.Choice(name=nome, value=valore) for valore, nome in _NOMI_AZIONI.items()]
    )
    async def dm(
        self, interaction: discord.Interaction, azione: app_commands.Choice[str], attivo: bool, testo: bool = False
    ) -> None:
        if not await self._controlli(interaction):
            return
        await opzioni.imposta_dm(interaction.guild.id, azione.value, attivo, interaction.user.id)
        if testo:
            attuale = (await opzioni.leggi(interaction.guild.id)).dm_testi.get(azione.value)
            titolo = await testo_per(interaction, "opzioni_dm_testo_titolo", azione=azione.name)
            campo = await testo_per(interaction, "opzioni_dm_testo_campo")
            await interaction.response.send_modal(ModuloTestoDm(azione.value, azione.name, attuale, titolo, campo))
            return
        await interaction.response.send_message(
            await testo_per(interaction, "opzioni_dm_per", name=azione.name, v2=(await testo_per(interaction, "opzioni_acceso")) if attivo else (await testo_per(interaction, "opzioni_spento"))), ephemeral=True
        )

    @comando_di_gruppo(
        "mod-sanzioni",
        nome="muto",
        descrizione="Sceglie o crea il ruolo del mute e rimette il blocco su tutti i canali.",
        sottogruppo=SOTTOGRUPPO,
    )
    @app_commands.describe(
        ruolo="Un ruolo che c'è già, da usare per il mute",
        nome_nuovo="Oppure crea un ruolo nuovo con questo nome",
        aggiorna="Rimette il blocco del mute sui canali che non l'hanno (fino a 500)",
    )
    async def muto(
        self,
        interaction: discord.Interaction,
        ruolo: discord.Role | None = None,
        nome_nuovo: app_commands.Range[str, 1, 100] | None = None,
        aggiorna: bool = False,
    ) -> None:
        """MOD-018: ruolo del mute scelto o creato dal server. MOD-019: aggiorna i canali."""
        if not await self._controlli(interaction):
            return
        guild = interaction.guild
        if ruolo is not None and nome_nuovo is not None:
            await interaction.response.send_message(await testo_per(interaction, "opzioni_muto_una_scelta"), ephemeral=True)
            return
        permessi_bot = guild.me.guild_permissions
        if (ruolo is not None or nome_nuovo is not None or aggiorna) and not permessi_bot.manage_roles:
            await interaction.response.send_message(await testo_per(interaction, "opzioni_muto_bot_senza_ruoli"), ephemeral=True)
            return
        if aggiorna and not permessi_bot.manage_channels:
            await interaction.response.send_message(await testo_per(interaction, "opzioni_muto_bot_senza_canali"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        cambiato = ruolo is not None or nome_nuovo is not None
        if ruolo is not None:
            rifiuto = check_role_assignable(guild, ruolo, interaction.user, self_service=True)
            if rifiuto is not None:
                await interaction.followup.send(rifiuto[:2000], ephemeral=True)
                return
        elif nome_nuovo is not None:
            try:
                ruolo = await guild.create_role(name=nome_nuovo.strip(), reason=audit_reason(f"Ruolo mute creato da {interaction.user}"))
            except discord.HTTPException:
                await interaction.followup.send(await testo_per(interaction, "opzioni_muto_creazione_fallita"), ephemeral=True)
                return
        if ruolo is not None:
            await db.set_guild_setting(guild.id, SETTING_MUTE_ROLE_ID, ruolo.id, changed_by=interaction.user.id)
        else:
            id_salvato = await db.get_guild_setting(guild.id, SETTING_MUTE_ROLE_ID)
            ruolo = guild.get_role(id_salvato) if id_salvato else None
            if ruolo is None:
                await interaction.followup.send(await testo_per(interaction, "opzioni_muto_nessun_ruolo"), ephemeral=True)
                return
        righe = [await testo_per(interaction, "opzioni_muto_ruolo", ruolo=ruolo.mention)]
        if aggiorna or cambiato:
            fatti, falliti = await aggiorna_ruolo_muto(guild, ruolo)
            righe.append(await testo_per(interaction, "opzioni_muto_canali", fatti=fatti, falliti=falliti))
        await interaction.followup.send("\n".join(righe)[:2000], ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @comando_di_gruppo(
        "mod-sanzioni",
        nome="aspetto",
        descrizione="Sceglie colore e icona di un tipo di caso nel log di moderazione.",
        sottogruppo=SOTTOGRUPPO,
    )
    @app_commands.describe(
        tipo="Il tipo di caso",
        colore="Colore, per esempio #c24a3a; «nessuno» toglie la scelta",
        icona="Emoji davanti al titolo; «nessuno» toglie la scelta",
    )
    @app_commands.choices(tipo=[app_commands.Choice(name=t, value=t) for t in moderation_aspetto.TIPI])
    async def aspetto(
        self,
        interaction: discord.Interaction,
        tipo: app_commands.Choice[str],
        colore: app_commands.Range[str, 4, 7] | None = None,
        icona: app_commands.Range[str, 1, 60] | None = None,
    ) -> None:
        """MOD-053: cambia solo il riquadro nel log. Colore e icona si controllano prima di salvare."""
        if not await self._controlli(interaction):
            return
        scelte = moderation_aspetto.pulita(await db.get_guild_setting(interaction.guild.id, moderation_aspetto.SETTING_ASPETTO))
        voce = dict(scelte.get(tipo.value, {}))
        if colore is not None:
            if colore.strip().lower() == "nessuno":
                voce.pop("colore", None)
            else:
                grezzo = colore.strip().lstrip("#")
                if len(grezzo) != 6 or any(c not in "0123456789abcdefABCDEF" for c in grezzo):
                    await interaction.response.send_message(await testo_per(interaction, "opzioni_aspetto_colore_no"), ephemeral=True)
                    return
                voce["colore"] = int(grezzo, 16)
        if icona is not None:
            if icona.strip().lower() == "nessuno":
                voce.pop("icona", None)
            elif not moderation_aspetto.icona_valida(icona):
                await interaction.response.send_message(await testo_per(interaction, "opzioni_aspetto_icona_no"), ephemeral=True)
                return
            else:
                voce["icona"] = icona.strip()
        if voce:
            scelte[tipo.value] = voce
        else:
            scelte.pop(tipo.value, None)
        await db.set_guild_setting(interaction.guild.id, moderation_aspetto.SETTING_ASPETTO, scelte, changed_by=interaction.user.id)
        colore_txt = f"#{voce['colore']:06x}" if "colore" in voce else "di base"
        await interaction.response.send_message(
            await testo_per(interaction, "opzioni_aspetto_salvato", tipo=tipo.value, colore=colore_txt, icona=voce.get("icona", "di base")),
            ephemeral=True, allowed_mentions=discord.AllowedMentions.none(),
        )

    @comando_di_gruppo(
        "mod-sanzioni",
        nome="memoria",
        descrizione="Accende lo storico dei nomi e il soprannome e il mute vocale ridati a chi rientra.",
        sottogruppo=SOTTOGRUPPO,
    )
    @app_commands.describe(
        nomi="Tiene i nomi e i soprannomi di ogni membro per 90 giorni (si legge con /mod-casi nomi)",
        persistenza="Chi esce e rientra entro 30 giorni riprende il soprannome e il mute vocale",
        registro_chat="Con warn, timeout, kick e ban salva gli ultimi 100 messaggi del canale (30 giorni)",
    )
    async def memoria(
        self, interaction: discord.Interaction, nomi: bool | None = None, persistenza: bool | None = None,
        registro_chat: bool | None = None,
    ) -> None:
        """MOD-103, MOD-104: spenti di base, sono dati personali con scadenza (registro dei dati)."""
        if not await self._controlli(interaction):
            return
        from core import moderation_nomi, moderation_registro_chat

        for chiave, valore in (
            (moderation_nomi.SETTING_STORICO_NOMI, nomi), (moderation_nomi.SETTING_PERSISTENZA, persistenza),
            (moderation_registro_chat.SETTING_REGISTRO_CHAT, registro_chat),
        ):
            if valore is not None:
                await db.set_guild_setting(interaction.guild.id, chiave, valore, changed_by=interaction.user.id)
        a = bool(await db.get_guild_setting(interaction.guild.id, moderation_nomi.SETTING_STORICO_NOMI))
        b = bool(await db.get_guild_setting(interaction.guild.id, moderation_nomi.SETTING_PERSISTENZA))
        c = bool(await db.get_guild_setting(interaction.guild.id, moderation_registro_chat.SETTING_REGISTRO_CHAT))
        await interaction.response.send_message(
            await testo_per(interaction, "opzioni_memoria_stato", nomi="sì" if a else "no", persistenza="sì" if b else "no", chat="sì" if c else "no"),
            ephemeral=True,
        )

    @comando_di_gruppo(
        "mod-sanzioni",
        nome="avvisi",
        descrizione="Scrive l'avviso delle sanzioni in un canale invece che nel messaggio privato.",
        sottogruppo=SOTTOGRUPPO,
    )
    @app_commands.describe(canale="Il canale degli avvisi (vuoto: si torna al messaggio privato)")
    async def avvisi(self, interaction: discord.Interaction, canale: discord.TextChannel | None = None) -> None:
        """MOD-060. Il bot deve poter scrivere e mettere embed nel canale."""
        if not await self._controlli(interaction):
            return
        if canale is not None:
            permessi = canale.permissions_for(interaction.guild.me)
            if not (permessi.view_channel and permessi.send_messages and permessi.embed_links):
                await interaction.response.send_message(
                    await testo_per(interaction, "opzioni_avvisi_bot_senza_permesso", canale=canale.mention), ephemeral=True
                )
                return
        await db.set_guild_setting(
            interaction.guild.id, SETTING_AVVISO_CANALE, canale.id if canale else None, changed_by=interaction.user.id
        )
        chiave = "opzioni_avvisi_in_canale" if canale else "opzioni_avvisi_in_dm"
        await interaction.response.send_message(
            await testo_per(interaction, chiave, canale=canale.mention if canale else ""),
            ephemeral=True, allowed_mentions=discord.AllowedMentions.none(),
        )

    @comando_di_gruppo(
        "mod-sanzioni",
        nome="azioni",
        descrizione="Dà a un ruolo il permesso di una sola azione di moderazione (o lo toglie).",
        sottogruppo=SOTTOGRUPPO,
    )
    @app_commands.describe(
        ruolo="Il ruolo. Vuoto: mostra chi ha già permessi",
        azione="L'azione. Vuoto con «togli»: le toglie tutte a quel ruolo",
        togli="Sì: toglie il permesso invece di darlo",
    )
    @app_commands.choices(azione=[app_commands.Choice(name=a, value=a) for a in permessi_azioni.AZIONI])
    async def azioni(
        self,
        interaction: discord.Interaction,
        ruolo: discord.Role | None = None,
        azione: app_commands.Choice[str] | None = None,
        togli: bool = False,
    ) -> None:
        """CFG-024. Restano sempre i controlli di gerarchia e il permesso del bot."""
        if not await self._controlli(interaction):
            return
        guild = interaction.guild
        if ruolo is None:
            dati = await permessi_azioni.elenco(guild.id)
            righe = [f"<@&{r}>: {', '.join(a)}" for r, a in dati.items()] or [await testo_per(interaction, "opzioni_azioni_nessuno")]
            await interaction.response.send_message(
                "\n".join(righe)[:1900], ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
            )
            return
        if togli:
            n = await permessi_azioni.togli(guild.id, ruolo.id, azione.value if azione else None)
            await interaction.response.send_message(
                await testo_per(interaction, "opzioni_azioni_tolte", n=n), ephemeral=True
            )
            return
        if azione is None:
            await interaction.response.send_message(await testo_per(interaction, "opzioni_azioni_serve_azione"), ephemeral=True)
            return
        errore = await permessi_azioni.concedi(guild, ruolo, azione.value, interaction.user)
        if errore:
            await interaction.response.send_message(errore[:1900], ephemeral=True)
            return
        await interaction.response.send_message(
            await testo_per(interaction, "opzioni_azioni_date", ruolo=ruolo.mention, azione=azione.value),
            ephemeral=True, allowed_mentions=discord.AllowedMentions.none(),
        )

    @comando_di_gruppo(
        "founder",
        nome="immuni",
        descrizione="Ruoli che la moderazione manuale non tocca (solo il proprietario).",
        sottogruppo=SOTTOGRUPPI["founder moderazione"],
    )
    @app_commands.describe(azione="Aggiungere o togliere", ruolo="Il ruolo")
    @app_commands.choices(
        azione=[
            app_commands.Choice(name="Aggiungi", value="aggiungi"),
            app_commands.Choice(name="Togli", value="togli"),
        ]
    )
    async def immuni(
        self, interaction: discord.Interaction, azione: app_commands.Choice[str], ruolo: discord.Role
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ACTIONS):
            return
        guild = interaction.guild
        # Decide chi si può moderare: lo sceglie solo il proprietario.
        if interaction.user.id != guild.owner_id:
            await interaction.response.send_message(
                await testo_per(interaction, "opzioni_ruoli_immuni_li_sceglie_solo"), ephemeral=True
            )
            return
        if ruolo.is_default():
            await interaction.response.send_message(await testo_per(interaction, "opzioni_everyone_non_puo_essere_immune"), ephemeral=True)
            return
        errore = await opzioni.cambia_ruolo_immune(
            guild.id, ruolo.id, azione.value == "aggiungi", interaction.user.id
        )
        if errore:
            await interaction.response.send_message(errore, ephemeral=True)
            return
        await interaction.response.send_message(
            await testo_per(interaction, "opzioni_warn_kick_ban_timeout_mute", mention=ruolo.mention, v2=(await testo_per(interaction, "opzioni_ora_immune")) if azione.value == 'aggiungi' else (await testo_per(interaction, "opzioni_non_piu_immune"))),
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(OpzioniModerazioneCog(bot))
