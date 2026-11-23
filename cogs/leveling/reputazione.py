"""
cogs/leveling/reputazione.py
============================
Reputazione tra membri: /rep (dai, togli, mostra, classifica, registro) e /admin-rep (imposta, cancella, azzera,
impostazioni, premio). Spenta di base. Pausa, tetto giornaliero e punti si scrivono in una transazione sola nel
repository; qui si leggono le interazioni, si controllano i ruoli, si dà la risposta e si allineano i ruoli per soglia.
Funzioni coperte: LIV-076, LIV-077, LIV-078, LIV-079, LIV-080, LIV-081, LIV-082, LIV-083, LIV-084, LIV-085, LIV-086, LIV-087, LIV-088
Dipende da: core/repositories/reputazione_repo.py, core/reputazione_logic.py
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from cogs.leveling._pagine import invia_lista
from cogs.leveling.leveling import _comando_rifiutato
from core.command_groups import CogConGruppi, comando_di_gruppo, togli_comandi_del_cog
from core.i18n import testo_per
from core.reputazione_logic import bersaglio_del_grazie, puo_agire, puo_togliere
from core.repositories.reputazione_repo import MAX_PREMI, reputazione_repo
from core.role_safety import check_role_assignable

logger = logging.getLogger("iyokai.reputazione")
SOLO_UTENTE = discord.AllowedMentions(users=True, roles=False, everyone=False)
NESSUNA_MENZIONE = discord.AllowedMentions.none()
PAROLA_AZZERA = "AZZERA"
MAX_CANALI_GRAZIE = 20


def _ids(membro: discord.Member) -> list[int]:
    return [r.id for r in getattr(membro, "roles", [])]


async def sincronizza_ruoli(guild: discord.Guild, membro: discord.Member) -> None:
    """Dà o toglie i ruoli per soglia secondo i punti attuali. Un ruolo non assegnabile si salta."""
    try:
        premi = await reputazione_repo.premi(guild.id)
        if not premi:
            return
        punti, _ = await reputazione_repo.punti_e_posizione(guild.id, membro.id)
        for soglia, role_id in premi:
            ruolo = guild.get_role(role_id)
            if ruolo is None or check_role_assignable(guild, ruolo, guild.me, self_service=True):
                continue
            ha = ruolo in membro.roles
            if punti >= soglia and not ha:
                await membro.add_roles(ruolo, reason="Reputazione: soglia raggiunta")
            elif punti < soglia and ha:
                await membro.remove_roles(ruolo, reason="Reputazione: sotto la soglia")
    except discord.HTTPException:
        logger.warning("Reputazione: ruoli per soglia non aggiornati (server %s, utente %s).", guild.id, membro.id)


class ReputazioneCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def cog_unload(self) -> None:
        togli_comandi_del_cog(self)

    # ---------------------------------------------------------------- dare e togliere
    async def _muovi(self, interaction: discord.Interaction, membro: discord.Member, punti: int, motivo: str | None) -> None:
        if await _comando_rifiutato(interaction):
            return
        g = interaction.guild
        if membro.bot or membro.id == interaction.user.id:
            await interaction.response.send_message(await testo_per(interaction, "rep_bersaglio"), ephemeral=True)
            return
        i = await reputazione_repo.impostazioni(g.id)
        if not i["attiva"]:
            await interaction.response.send_message(await testo_per(interaction, "rep_spenta"), ephemeral=True)
            return
        if not puo_agire(_ids(interaction.user), i["ruolo_dare_richiesto"], i["ruolo_dare_escluso"]):
            await interaction.response.send_message(await testo_per(interaction, "rep_non_puoi_dare"), ephemeral=True)
            return
        if not puo_agire(_ids(membro), i["ruolo_ricevere_richiesto"], i["ruolo_ricevere_escluso"]):
            await interaction.response.send_message(await testo_per(interaction, "rep_non_puo_ricevere"), ephemeral=True)
            return
        if punti < 0 and not puo_togliere(_ids(interaction.user), i["ruolo_togliere"], interaction.user.guild_permissions.manage_guild):
            await interaction.response.send_message(await testo_per(interaction, "rep_non_puoi_togliere"), ephemeral=True)
            return
        esito = await reputazione_repo.muovi(g.id, interaction.user.id, membro.id, punti, motivo=(motivo or "").strip())
        if esito.stato != "ok":
            await interaction.response.send_message(
                await testo_per(interaction, f"rep_{esito.stato}", massimo=i["massimo_per_comando"], tetto=i["tetto_giornaliero"], ore=max(1, esito.attesa // 3600), minuti=max(1, esito.attesa // 60), nome=i["nome"]),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            await testo_per(interaction, "rep_dato" if punti > 0 else "rep_tolto", utente=interaction.user.mention, membro=membro.mention, n=abs(punti), nome=i["nome"], totale=esito.punti, pubblica=True),
            allowed_mentions=SOLO_UTENTE,
        )
        await sincronizza_ruoli(g, membro)

    @comando_di_gruppo("rep", nome="dai", descrizione="Dai punti reputazione a un membro.")
    @app_commands.describe(membro="Chi li riceve", punti="Quanti punti (il massimo lo sceglie il server)", motivo="Perché (facoltativo)")
    async def dai(self, interaction: discord.Interaction, membro: discord.Member, punti: app_commands.Range[int, 1, 10] = 1, motivo: app_commands.Range[str, 1, 100] | None = None) -> None:
        await self._muovi(interaction, membro, punti, motivo)

    @comando_di_gruppo("rep", nome="togli", descrizione="Togli punti reputazione a un membro (solo chi ha il ruolo scelto dal server).")
    @app_commands.describe(membro="A chi li togli", punti="Quanti punti", motivo="Perché (facoltativo)")
    async def togli(self, interaction: discord.Interaction, membro: discord.Member, punti: app_commands.Range[int, 1, 10] = 1, motivo: app_commands.Range[str, 1, 100] | None = None) -> None:
        await self._muovi(interaction, membro, -punti, motivo)

    # ---------------------------------------------------------------- lettura
    @comando_di_gruppo("rep", nome="mostra", descrizione="Reputazione e posizione di un membro (senza nome: la tua).")
    @app_commands.describe(membro="Di chi")
    async def mostra(self, interaction: discord.Interaction, membro: discord.Member | None = None) -> None:
        if await _comando_rifiutato(interaction):
            return
        membro = membro or interaction.user
        i = await reputazione_repo.impostazioni(interaction.guild.id)
        punti, pos = await reputazione_repo.punti_e_posizione(interaction.guild.id, membro.id)
        chiave = "rep_mostra" if pos else "rep_mostra_zero"
        await interaction.response.send_message(
            await testo_per(interaction, chiave, membro=membro.mention, punti=punti, pos=pos or 0, nome=i["nome"], pubblica=True), ephemeral=not i["attiva"], allowed_mentions=NESSUNA_MENZIONE
        )

    @comando_di_gruppo("rep", nome="classifica", descrizione="Classifica della reputazione del server.")
    async def classifica(self, interaction: discord.Interaction) -> None:
        if await _comando_rifiutato(interaction):
            return
        await interaction.response.defer()
        i = await reputazione_repo.impostazioni(interaction.guild.id)
        righe = [f"**{n}.** <@{u}> — {p}" for n, (u, p) in enumerate(await reputazione_repo.classifica(interaction.guild.id), 1)]
        if not righe:
            await interaction.followup.send(await testo_per(interaction, "rep_vuota"), ephemeral=True)
            return
        await invia_lista(interaction, f"🏅 {i['nome']}", righe, discord.Color.dark_gold())

    @comando_di_gruppo("rep", nome="registro", descrizione="Chi ha dato o tolto reputazione (la tua; lo staff può vedere quella di altri).")
    @app_commands.describe(membro="Di chi (solo lo staff)")
    async def registro(self, interaction: discord.Interaction, membro: discord.Member | None = None) -> None:
        if await _comando_rifiutato(interaction):
            return
        if membro is not None and membro.id != interaction.user.id and not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(await testo_per(interaction, "rep_registro_staff"), ephemeral=True)
            return
        membro = membro or interaction.user
        voci = await reputazione_repo.registro(interaction.guild.id, membro.id)
        if not voci:
            await interaction.response.send_message(await testo_per(interaction, "rep_vuota"), ephemeral=True)
            return
        righe = [
            f"<t:{int(v['creato'].timestamp())}:d> <@{v['da_id']}> → <@{v['a_id']}> **{v['delta']:+d}**" + (f" — {v['motivo']}" if v["motivo"] else "")
            for v in voci
        ]
        await interaction.response.send_message("\n".join(righe)[:1900], ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)

    # ---------------------------------------------------------------- staff
    @comando_di_gruppo("admin-rep", nome="imposta", descrizione="Fissa i punti reputazione di un membro.")
    @app_commands.describe(membro="Di chi", punti="Punti (anche negativi)")
    async def imposta(self, interaction: discord.Interaction, membro: discord.Member, punti: app_commands.Range[int, -1_000_000, 1_000_000]) -> None:
        if await _comando_rifiutato(interaction):
            return
        if membro.bot:
            await interaction.response.send_message(await testo_per(interaction, "rep_bersaglio"), ephemeral=True)
            return
        await reputazione_repo.imposta_punti(interaction.guild.id, membro.id, punti, interaction.user.id)
        await interaction.response.send_message(await testo_per(interaction, "rep_staff_ok", membro=membro.mention, punti=punti), ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)
        await sincronizza_ruoli(interaction.guild, membro)

    @comando_di_gruppo("admin-rep", nome="cancella", descrizione="Porta a zero la reputazione di un membro.")
    @app_commands.describe(membro="Di chi")
    async def cancella(self, interaction: discord.Interaction, membro: discord.Member) -> None:
        if await _comando_rifiutato(interaction):
            return
        await reputazione_repo.cancella(interaction.guild.id, membro.id, interaction.user.id)
        await interaction.response.send_message(await testo_per(interaction, "rep_staff_ok", membro=membro.mention, punti=0), ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)
        await sincronizza_ruoli(interaction.guild, membro)

    @comando_di_gruppo("admin-rep", nome="azzera", descrizione="Azzera la reputazione di tutto il server (serve la parola di conferma).")
    @app_commands.describe(conferma=f"Scrivi {PAROLA_AZZERA} per confermare")
    async def azzera(self, interaction: discord.Interaction, conferma: app_commands.Range[str, 1, 20]) -> None:
        if await _comando_rifiutato(interaction):
            return
        if conferma.strip() != PAROLA_AZZERA:
            await interaction.response.send_message(await testo_per(interaction, "rep_azzera_parola", parola=PAROLA_AZZERA), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        premi = await reputazione_repo.premi(interaction.guild.id)
        n = await reputazione_repo.azzera_server(interaction.guild.id)
        for _, rid in premi:  # chi aveva un ruolo per soglia lo perde
            ruolo = interaction.guild.get_role(rid)
            if ruolo is None or check_role_assignable(interaction.guild, ruolo, interaction.guild.me, self_service=True):
                continue
            for m in list(ruolo.members)[:500]:
                try:
                    await m.remove_roles(ruolo, reason="Reputazione azzerata")
                except discord.HTTPException:
                    break
        await interaction.followup.send(await testo_per(interaction, "rep_azzerata", n=n), ephemeral=True)

    @comando_di_gruppo("admin-rep", nome="impostazioni", descrizione="Accendi la reputazione e scegli nome, pausa, limiti, ruoli e «grazie».")
    @app_commands.describe(
        attiva="Accendi o spegni la reputazione", nome="Nome dei punti (max 20 caratteri)", pausa_ore="Ore di pausa tra un comando e l'altro (1-168)",
        massimo="Punti al massimo per comando (1-10)", tetto="Punti al massimo per persona ogni 24 ore (1-100)",
        ruolo_togliere="Chi ha questo ruolo può togliere punti", dare_richiesto="Per dare serve questo ruolo", dare_escluso="Chi ha questo ruolo non può dare",
        ricevere_richiesto="Per ricevere serve questo ruolo", ricevere_escluso="Chi ha questo ruolo non può ricevere",
        togli_ruoli="Sì = togli tutte le scelte sui ruoli", grazie="Accendi «grazie @utente»", grazie_canale="Aggiungi o togli un canale dove vale «grazie»",
    )
    async def impostazioni(
        self, interaction: discord.Interaction, attiva: bool | None = None, nome: app_commands.Range[str, 1, 20] | None = None,
        pausa_ore: app_commands.Range[int, 1, 168] | None = None, massimo: app_commands.Range[int, 1, 10] | None = None,
        tetto: app_commands.Range[int, 1, 100] | None = None, ruolo_togliere: discord.Role | None = None,
        dare_richiesto: discord.Role | None = None, dare_escluso: discord.Role | None = None,
        ricevere_richiesto: discord.Role | None = None, ricevere_escluso: discord.Role | None = None,
        togli_ruoli: bool | None = None, grazie: bool | None = None, grazie_canale: discord.TextChannel | None = None,
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        g = interaction.guild.id
        campi: dict = {}
        for chiave, valore in {"attiva": attiva, "nome": nome.strip() if nome else None, "massimo_per_comando": massimo, "tetto_giornaliero": tetto, "grazie_attivo": grazie}.items():
            if valore is not None and valore != "":
                campi[chiave] = valore
        if pausa_ore is not None:
            campi["pausa_secondi"] = pausa_ore * 3600
        for chiave, ruolo in {"ruolo_togliere": ruolo_togliere, "ruolo_dare_richiesto": dare_richiesto, "ruolo_dare_escluso": dare_escluso,
                              "ruolo_ricevere_richiesto": ricevere_richiesto, "ruolo_ricevere_escluso": ricevere_escluso}.items():
            if ruolo is not None:
                if ruolo.is_default():
                    await interaction.response.send_message(await testo_per(interaction, "rep_ruolo_non_valido"), ephemeral=True)
                    return
                campi[chiave] = ruolo.id
        if togli_ruoli:
            for chiave in ("ruolo_togliere", "ruolo_dare_richiesto", "ruolo_dare_escluso", "ruolo_ricevere_richiesto", "ruolo_ricevere_escluso"):
                campi[chiave] = None
        if grazie_canale is not None:
            canali = list((await reputazione_repo.impostazioni(g))["grazie_canali"])
            if grazie_canale.id in canali:
                canali.remove(grazie_canale.id)
            elif len(canali) < MAX_CANALI_GRAZIE:
                canali.append(grazie_canale.id)
            else:
                await interaction.response.send_message(await testo_per(interaction, "rep_troppi_canali", massimo=MAX_CANALI_GRAZIE), ephemeral=True)
                return
            campi["grazie_canali"] = canali
        if campi:
            await reputazione_repo.imposta(g, **campi)
        i = await reputazione_repo.impostazioni(g)
        stato = await testo_per(
            interaction, "rep_impostazioni", attiva="✅" if i["attiva"] else "❌", nome=i["nome"], ore=i["pausa_secondi"] // 3600, massimo=i["massimo_per_comando"], tetto=i["tetto_giornaliero"],
            togliere=f"<@&{i['ruolo_togliere']}>" if i["ruolo_togliere"] else "—", grazie="✅" if i["grazie_attivo"] else "❌",
            canali=" ".join(f"<#{c}>" for c in i["grazie_canali"]) or "—",
        )
        await interaction.response.send_message(stato[:1900], ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)

    @comando_di_gruppo("admin-rep", nome="premio", descrizione="Ruoli dati a una soglia di reputazione (senza soglia: l'elenco).")
    @app_commands.describe(soglia="Punti da raggiungere", ruolo="Il ruolo da dare", togli="Sì = togli il premio di questa soglia")
    async def premio(self, interaction: discord.Interaction, soglia: app_commands.Range[int, 1, 1_000_000] | None = None, ruolo: discord.Role | None = None, togli: bool = False) -> None:
        if await _comando_rifiutato(interaction):
            return
        g = interaction.guild.id
        if soglia is None:
            premi = await reputazione_repo.premi(g)
            testo = "\n".join(f"{s}: <@&{r}>" for s, r in premi) or await testo_per(interaction, "rep_nessun_premio")
            await interaction.response.send_message(testo[:1900], ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)
            return
        if togli:
            fatto = await reputazione_repo.togli_premio(g, soglia)
            await interaction.response.send_message(await testo_per(interaction, "rep_premio_tolto" if fatto else "rep_nessun_premio"), ephemeral=True)
            return
        if ruolo is None:
            await interaction.response.send_message(await testo_per(interaction, "rep_serve_ruolo"), ephemeral=True)
            return
        motivo = check_role_assignable(interaction.guild, ruolo, interaction.user, self_service=True)
        if motivo:
            await interaction.response.send_message(motivo[:1900], ephemeral=True)
            return
        esito = await reputazione_repo.metti_premio(g, soglia, ruolo.id)
        await interaction.response.send_message(await testo_per(interaction, f"rep_premio_{esito}", massimo=MAX_PREMI), ephemeral=True)

    # ---------------------------------------------------------------- «grazie @utente» (LIV-078)
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot or not message.mentions:
            return
        bersaglio = bersaglio_del_grazie(message.content, [(m.id, m.bot) for m in message.mentions], message.author.id)
        if bersaglio is None:
            return
        try:
            i = await reputazione_repo.impostazioni(message.guild.id)
            if not (i["attiva"] and i["grazie_attivo"]) or message.channel.id not in i["grazie_canali"]:
                return
            membro = message.mentions[0]
            if not isinstance(membro, discord.Member):
                return
            if not (puo_agire(_ids(message.author), i["ruolo_dare_richiesto"], i["ruolo_dare_escluso"])
                    and puo_agire(_ids(membro), i["ruolo_ricevere_richiesto"], i["ruolo_ricevere_escluso"])):
                return
            esito = await reputazione_repo.muovi(message.guild.id, message.author.id, bersaglio, 1, fonte="grazie")
            if esito.stato == "ok":
                await message.add_reaction("🙏")
                await sincronizza_ruoli(message.guild, membro)
        except Exception:  # un «grazie» non deve mai rompere il messaggio
            logger.exception("Reputazione: errore nel «grazie»")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ReputazioneCog(bot))
