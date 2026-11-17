"""
cogs/utility/server_stats.py
================================
Server Stats: `/utility serverstats` mostra i numeri del server, i grafici (messaggi, vocale, canale, membro,
membri nel tempo, ingressi e uscite, online), le classifiche, la ritenzione e le fonti degli ingressi; si può
avere anche il CSV. Due menu col tasto destro (membro, canale). Solo chi ha il permesso scelto dall'admin vede.
Funzioni coperte: SPEC §14.18; STA-001..005, 007, 008, 010, 011, 013..024, 053..056
Dipende da: core/repositories/activity_stats_repo.py (conteggi), core/server_stats_image.py (grafici)
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.i18n import lingua_interazione, t, testo_per
from core.ui_base import BaseView
from core.premium import PremiumModule, registry
from core.repositories.activity_stats_repo import activity_stats_repo
from core.repositories.citazioni_repo import comandi_uso_repo
from core.repositories.event_log_repo import event_log_repo
from core.repositories.invite_stats_repo import invite_stats_repo
from core.safe_image import run_image_task
from core.server_stats_image import render_bar_chart, render_growth_chart, render_line_chart
from core.activity_stats_logic import per_giorno_settimana
from core.server_stats_logic import (
    compute_daily_net_change,
    fill_missing_days,
    ritenzione,
    tabella_in_csv,
    totale_membri_per_giorno,
)

MODULE_SERVER_STATS = "server_stats"
DEFAULT_DAYS = 14


VISTE = {
    "crescita": "Crescita netta dei membri",
    "ingressi": "Ingressi per giorno",
    "uscite": "Uscite per giorno",
    "canali": "Canali più attivi",
    "membri": "Membri più attivi",
    "ore": "Attività per ora del giorno",
    "giorni-settimana": "Attività per giorno della settimana",
    "membro": "Attività di un membro",
    "panoramica": "Panoramica del server",
    "messaggi": "Messaggi per giorno",
    "vocale": "Minuti in vocale per giorno",
    "canale": "Attività di un canale",
    "totale-membri": "Numero di membri nel tempo",
    "ingressi-uscite": "Ingressi e uscite insieme",
    "ritenzione": "Chi resta dopo l'ingresso",
    "fonti": "Da dove arrivano i nuovi membri",
    "inviti": "Inviti e invitanti migliori",
    "online": "Membri online nel tempo",
    "giochi": "A cosa giocano i membri",
}
_NOMI_GIORNI = ("Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom")
_UNITA = {"messages": "messaggi", "voice_minutes": "minuti in vocale", "comandi": "usi"}
RIGHE_CLASSIFICA = 10
PERIODI_BOTTONI = (7, 30, 90)
_NESSUNA_MENZIONE = discord.AllowedMentions.none()
MAX_GIORNI = 90
NOME_ANONIMO_CHIAVE = "stv_anonimo"


@dataclass
class Vista:
    """Il risultato di una vista: l'embed, il grafico (PNG) e i numeri in forma di tabella (per il CSV)."""

    embed: discord.Embed
    png: bytes | None = None
    intestazione: list[str] = field(default_factory=list)
    righe: list[list] = field(default_factory=list)


def _canale_visibile(guild: discord.Guild, canale_id: int, membro: discord.Member) -> bool:
    canale = guild.get_channel(canale_id)
    return canale is None or canale.permissions_for(membro).view_channel


def puo_vedere(membro, view_roles: list[int]) -> bool:
    """STA-013: chi gestisce il server vede sempre; se l'admin ha scelto dei ruoli, solo chi ne ha uno."""
    if not view_roles:
        return True
    permessi = getattr(membro, "guild_permissions", None)
    if permessi is not None and (permessi.administrator or permessi.manage_guild):
        return True
    return bool({r.id for r in getattr(membro, "roles", ())} & set(view_roles))


async def _eventi_giornalieri(guild_id: int, since: datetime, tipo: str) -> dict:
    eventi = await event_log_repo.get_events_by_type_since(guild_id, tipo, since)
    conteggi: dict = {}
    for e in eventi:
        conteggi[e.created_at.date()] = conteggi.get(e.created_at.date(), 0) + 1
    return conteggi


def _campi_server(embed: discord.Embed, guild: discord.Guild, ruolo, _) -> None:
    embed.add_field(name=_("membri"), value=str(guild.member_count), inline=True)
    embed.add_field(
        name=_("canali"),
        value=(
            f"{len(guild.text_channels)} testo\n{len(guild.voice_channels)} vocali\n"
            f"{len(guild.forums)} forum\n{len(guild.stage_channels)} stage\n{len(guild.categories)} categorie"
        ),
        inline=True,
    )
    embed.add_field(name=_("ruoli"), value=str(len(guild.roles)), inline=True)
    embed.add_field(name="Emoji", value=f"{len(guild.emojis)} / {guild.emoji_limit}", inline=True)
    embed.add_field(name="Boost", value=f"Livello {guild.premium_tier} ({guild.premium_subscription_count} boost)", inline=True)
    embed.add_field(name=_("creato_il"), value=discord.utils.format_dt(guild.created_at, style="D"), inline=True)
    if ruolo is not None:
        con = len(ruolo.members)
        embed.add_field(name=_("con_ruolo", nome=ruolo.name[:60]), value=_("con_senza", con=con, senza=max(0, guild.member_count - con)), inline=False)
    if guild.icon is not None:
        embed.set_thumbnail(url=guild.icon.url)


async def _chiavi_anonime(ids: list[int]) -> set[int]:
    """STA-028: chi ha scelto di comparire come «utente anonimo»."""
    return await activity_stats_repo.anonymous_among(ids)


async def costruisci_vista(
    guild: discord.Guild,
    vista: str,
    giorni: int,
    metrica: str = "messages",
    ruolo: discord.Role | None = None,
    utente: discord.Member | None = None,
    visti_da: discord.Member | None = None,
    canale=None,
    presenze: bool = False,
    lingua: str = "it",
) -> Vista:
    """Embed, grafico e tabella di /utility serverstats per la vista scelta (STA-001..005, 009, 014..024, 053..055)."""
    def _(chiave: str, **valori) -> str:
        return t(f"stv_{chiave}", lingua, **valori)

    adesso = datetime.now(timezone.utc)
    giorni = max(1, min(giorni, MAX_GIORNI))
    since = adesso - timedelta(days=giorni)
    dal = (adesso - timedelta(days=giorni - 1)).date()
    embed = discord.Embed(title=f"📊 {_('vista_' + vista)} — {guild.name}"[:256], color=discord.Color.blurple())
    risultato = Vista(embed)
    unita = _UNITA[metrica]
    embed.set_footer(text=_("ultimi_giorni", giorni=giorni))

    if metrica == "comandi":  # comandi più usati (D69 B16): la classifica vale per tutte le viste
        top = await comandi_uso_repo.piu_usati(guild.id, dal, RIGHE_CLASSIFICA)
        embed.description = "\n".join(f"{i}. `/{c}` — **{n}** {unita}" for i, (c, n) in enumerate(top, 1)) or _("nessun_dato")
        risultato.intestazione, risultato.righe = ["comando", "usi"], [[c, n] for c, n in top]
        return risultato

    serie_giorni = [dal + timedelta(days=i) for i in range((adesso.date() - dal).days + 1)]

    def _asse(per_giorno: dict) -> list[int]:
        return [per_giorno.get(g, 0) for g in serie_giorni]

    async def _grafico_giorni(per_giorno: dict, titolo: str) -> None:
        valori = _asse(per_giorno)
        risultato.png = await run_image_task(render_bar_chart, [g.strftime("%d/%m") for g in serie_giorni], valori, titolo)
        risultato.intestazione = ["giorno", "valore"]
        risultato.righe = [[g.isoformat(), v] for g, v in zip(serie_giorni, valori)]

    if vista in ("crescita", "ingressi", "uscite"):
        if vista == "crescita":
            ev = await event_log_repo.get_events_by_type_since(guild.id, "member_join", since)
            ev2 = await event_log_repo.get_events_by_type_since(guild.id, "member_remove", since)
            grezze = compute_daily_net_change(
                [(e.created_at, "member_join") for e in ev] + [(e.created_at, "member_remove") for e in ev2]
            )
        else:
            tipo = "member_join" if vista == "ingressi" else "member_remove"
            segno = 1 if vista == "ingressi" else -1
            grezze = {g: segno * n for g, n in (await _eventi_giornalieri(guild.id, since, tipo)).items()}
        serie = fill_missing_days(grezze, start=since.date(), end=adesso.date())
        risultato.png = await run_image_task(render_growth_chart, serie, f"{VISTE[vista]} — ultimi {giorni} giorni")
        risultato.intestazione, risultato.righe = ["giorno", "variazione"], [[g.isoformat(), v] for g, v in sorted(serie.items())]
        _campi_server(embed, guild, ruolo, _)
    elif vista == "panoramica":  # STA-001
        messaggi = await activity_stats_repo.by_day(guild.id, dal, "messages")
        vocale = await activity_stats_repo.by_day(guild.id, dal, "voice_minutes")
        entrati = await _eventi_giornalieri(guild.id, since, "member_join")
        usciti = await _eventi_giornalieri(guild.id, since, "member_remove")
        embed.add_field(name=_("membri"), value=str(guild.member_count), inline=True)
        embed.add_field(name=_("messaggi"), value=str(sum(messaggi.values())), inline=True)
        embed.add_field(name=_("minuti_vocale"), value=str(sum(vocale.values())), inline=True)
        embed.add_field(name=_("ingressi"), value=str(sum(entrati.values())), inline=True)
        embed.add_field(name=_("uscite"), value=str(sum(usciti.values())), inline=True)
        top = await activity_stats_repo.top_channels(guild.id, dal, "messages", RIGHE_CLASSIFICA * 5)
        if visti_da is not None:
            top = [(c, n) for c, n in top if _canale_visibile(guild, c, visti_da)]
        if top:
            embed.add_field(name=_("canale_top"), value=f"<#{top[0][0]}> ({top[0][1]})", inline=True)
        await _grafico_giorni(messaggi, _("titolo_messaggi"))
        risultato.intestazione = ["giorno", "messaggi", "minuti_vocale", "ingressi", "uscite"]
        risultato.righe = [[g.isoformat(), messaggi.get(g, 0), vocale.get(g, 0), entrati.get(g, 0), usciti.get(g, 0)] for g in serie_giorni]
    elif vista in ("messaggi", "vocale"):  # STA-002, 003, 014, 015
        misura = "messages" if vista == "messaggi" else "voice_minutes"
        per_giorno = await activity_stats_repo.by_day(guild.id, dal, misura)
        embed.description = _("totale_periodo", n=sum(per_giorno.values()), unita=_UNITA[misura])
        if vista == "vocale":
            stati = await activity_stats_repo.voice_states(guild.id, dal)
            embed.add_field(name=_("per_stato"), value=_("stati", **stati), inline=False)  # STA-006
        await _grafico_giorni(per_giorno, f"{_UNITA[misura]} — {giorni}")
    elif vista == "canale":  # STA-004, 016
        if canale is None:
            embed.description = _("scegli_canale")
        elif visti_da is not None and not canale.permissions_for(visti_da).view_channel:
            embed.description = _("canale_non_visibile")
        else:
            misura = metrica
            if misura == "messages" and isinstance(canale, (discord.VoiceChannel, discord.StageChannel)):
                misura = "voice_minutes"
            per_giorno = await activity_stats_repo.by_day_for_channel(guild.id, canale.id, dal, misura)
            embed.description = f"{canale.mention}: " + _("totale_periodo", n=sum(per_giorno.values()), unita=_UNITA[misura])
            await _grafico_giorni(per_giorno, f"{_UNITA[misura]} — {getattr(canale, 'name', '')[:40]}")
    elif vista == "canali":
        top = await activity_stats_repo.top_channels(guild.id, dal, metrica, RIGHE_CLASSIFICA * 5)
        if visti_da is not None:  # chi guarda non vede nomi e numeri dei canali che non può aprire
            top = [(c, n) for c, n in top if _canale_visibile(guild, c, visti_da)]
        top = top[:RIGHE_CLASSIFICA]
        embed.description = "\n".join(f"{i}. <#{c}> — **{n}** {unita}" for i, (c, n) in enumerate(top, 1)) or _("nessun_dato")
        risultato.intestazione, risultato.righe = ["canale_id", "valore"], [[c, n] for c, n in top]
    elif vista == "membri":
        solo = {m.id for m in ruolo.members} if ruolo is not None else None
        top = await activity_stats_repo.top_members(guild.id, dal, metrica, RIGHE_CLASSIFICA, solo_utenti=solo)
        anonimi = await _chiavi_anonime([u for u, _n in top])
        etichetta = lambda u: _("anonimo") if u in anonimi else f"<@{u}>"  # noqa: E731  STA-028
        embed.description = "\n".join(f"{i}. {etichetta(u)} — **{n}** {unita}" for i, (u, n) in enumerate(top, 1)) or _("nessun_dato")
        risultato.intestazione, risultato.righe = ["posizione", "membro_id", "valore"], [
            [i, 0 if u in anonimi else u, n] for i, (u, n) in enumerate(top, 1)
        ]
        if ruolo is not None:
            embed.set_footer(text=_("solo_ruolo", nome=ruolo.name[:60]))
    elif vista == "ore":
        ore = await activity_stats_repo.by_hour(guild.id, dal, metrica)
        risultato.png = await run_image_task(render_bar_chart, [str(h) for h in range(24)], ore, f"{unita} per ora (UTC)")
        risultato.intestazione, risultato.righe = ["ora_utc", "valore"], [[h, v] for h, v in enumerate(ore)]
        embed.set_footer(text=_("ultimi_giorni_utc", giorni=giorni))
    elif vista == "giorni-settimana":
        per_giorno = await activity_stats_repo.by_day(guild.id, dal, metrica)
        totali = per_giorno_settimana(per_giorno)
        risultato.png = await run_image_task(render_bar_chart, list(_NOMI_GIORNI), totali, f"{unita} per giorno della settimana")
        risultato.intestazione, risultato.righe = ["giorno_settimana", "valore"], [[n, v] for n, v in zip(_NOMI_GIORNI, totali)]
    elif vista == "membro":  # STA-005 (anche le proprie), 017
        bersaglio = utente or visti_da
        if bersaglio is None:
            embed.description = _("scegli_membro")
        elif await activity_stats_repo.is_anonymous(bersaglio.id) and (visti_da is None or visti_da.id != bersaglio.id):
            embed.description = _("membro_anonimo")  # STA-028: nemmeno guardando il singolo membro
        else:
            mess = await activity_stats_repo.member_total(guild.id, bersaglio.id, dal, "messages")
            voce = await activity_stats_repo.member_total(guild.id, bersaglio.id, dal, "voice_minutes")
            embed.description = _("membro_totali", mention=bersaglio.mention, mess=mess, voce=voce)
            stati = await activity_stats_repo.voice_states(guild.id, dal, bersaglio.id)
            if any(stati.values()):
                embed.add_field(name=_("per_stato"), value=_("stati", **stati), inline=False)
            misura = metrica if metrica in ("messages", "voice_minutes") else "messages"
            per_giorno = await activity_stats_repo.by_day_for_member(guild.id, bersaglio.id, dal, misura)
            await _grafico_giorni(per_giorno, f"{_UNITA[misura]} — {getattr(bersaglio, 'display_name', '')[:30]}")
            risultato.intestazione = ["giorno", "valore"]
    elif vista in ("totale-membri", "ingressi-uscite"):  # STA-018, 019
        entrati = await _eventi_giornalieri(guild.id, since, "member_join")
        usciti = await _eventi_giornalieri(guild.id, since, "member_remove")
        etichette = [g.strftime("%d/%m") for g in serie_giorni]
        if vista == "totale-membri":
            variazioni = {g: entrati.get(g, 0) - usciti.get(g, 0) for g in serie_giorni}
            totale = totale_membri_per_giorno(guild.member_count or 0, variazioni, dal, adesso.date())
            valori = [totale[g] for g in serie_giorni]
            risultato.png = await run_image_task(render_line_chart, etichette, [(_("membri"), valori)], _("vista_totale-membri"))
            risultato.intestazione, risultato.righe = ["giorno", "membri"], [[g.isoformat(), v] for g, v in zip(serie_giorni, valori)]
        else:
            a, b = _asse(entrati), _asse(usciti)
            risultato.png = await run_image_task(render_line_chart, etichette, [(_("ingressi"), a), (_("uscite"), b)], _("vista_ingressi-uscite"))
            risultato.intestazione, risultato.righe = ["giorno", "ingressi", "uscite"], [[g.isoformat(), x, y] for g, x, y in zip(serie_giorni, a, b)]
        embed.add_field(name=_("membri"), value=str(guild.member_count), inline=True)
        embed.set_footer(text=_("da_registro", giorni=giorni))
    elif vista == "ritenzione":  # STA-053
        ingressi = [(e.target_user_id, e.created_at) for e in await event_log_repo.get_events_by_type_since(guild.id, "member_join", since) if e.target_user_id]
        uscite = [(e.target_user_id, e.created_at) for e in await event_log_repo.get_events_by_type_since(guild.id, "member_remove", since) if e.target_user_id]
        r = ritenzione(ingressi, uscite, adesso)
        embed.description = _("ritenzione_testo", **r) if r["ingressi"] else _("nessun_dato")
        if r["dopo_7g_restano"] is not None:
            embed.add_field(name=_("dopo_7g"), value=f"{r['dopo_7g_restano']}%", inline=False)
        risultato.intestazione, risultato.righe = list(r.keys()), [list(r.values())]
    elif vista == "fonti":  # STA-054
        fonti = await invite_stats_repo.per_fonte_dal(guild.id, since)
        totale = sum(fonti.values())
        embed.description = "\n".join(
            f"**{_('fonte_' + k) if k in ('normale', 'vanity', 'personale', 'sconosciuto') else k[:30]}** — {n} ({round(100 * n / totale)}%)"
            for k, n in sorted(fonti.items(), key=lambda x: -x[1])
        ) or _("nessun_dato")
        risultato.intestazione, risultato.righe = ["fonte", "ingressi"], [[k, n] for k, n in sorted(fonti.items())]
    elif vista == "inviti":  # STA-055
        invitanti, codici = await invite_stats_repo.top_nel_periodo(guild.id, since)
        anonimi = await _chiavi_anonime([u for u, _n in invitanti])
        embed.add_field(
            name=_("invitanti"),
            value="\n".join(f"{i}. {_('anonimo') if u in anonimi else f'<@{u}>'} — **{n}**" for i, (u, n) in enumerate(invitanti, 1)) or _("nessun_dato"),
            inline=False,
        )
        embed.add_field(
            name=_("codici"),
            value="\n".join(f"{i}. `{c[:32].replace('`', '')}` — **{n}**" for i, (c, n) in enumerate(codici, 1)) or _("nessun_dato"),
            inline=False,
        )
        risultato.intestazione = ["tipo", "id_o_codice", "ingressi"]
        risultato.righe = [["invitante", 0 if u in anonimi else u, n] for u, n in invitanti] + [["codice", c, n] for c, n in codici]
    elif vista == "online":  # STA-008
        campioni = await activity_stats_repo.online_samples(guild.id, since)
        if not campioni:
            embed.description = _("online_vuoto")
        else:
            risultato.png = await run_image_task(
                render_line_chart, [c[0].strftime("%d/%m %H") for c in campioni], [(_("online"), [c[1] for c in campioni])], _("vista_online")
            )
            risultato.intestazione, risultato.righe = ["ora_utc", "online"], [[c[0].isoformat(), c[1]] for c in campioni]
    else:  # giochi (STA-007): una fotografia di adesso, non si salva nulla
        if not presenze:
            embed.description = _("giochi_senza_intent")
        else:
            conteggio: dict[str, int] = {}
            for m in guild.members:
                if m.bot:
                    continue
                for a in m.activities:
                    if a.type in (discord.ActivityType.playing, discord.ActivityType.competing) and getattr(a, "name", None):
                        nome = discord.utils.escape_markdown(discord.utils.escape_mentions(a.name))[:40]
                        conteggio[nome] = conteggio.get(nome, 0) + 1
            top = sorted(conteggio.items(), key=lambda x: (-x[1], x[0]))[:RIGHE_CLASSIFICA]
            embed.description = "\n".join(f"{i}. **{n}** — {c}" for i, (n, c) in enumerate(top, 1)) or _("nessun_dato")
            risultato.intestazione, risultato.righe = ["gioco", "membri"], [[n, c] for n, c in top]
            embed.set_footer(text=_("adesso"))
    if risultato.png is not None:
        embed.set_image(url="attachment://statistiche.png")
    return risultato


async def costruisci_statistiche(
    guild: discord.Guild,
    vista: str,
    giorni: int,
    metrica: str = "messages",
    ruolo: discord.Role | None = None,
    utente: discord.Member | None = None,
    visti_da: discord.Member | None = None,
    canale=None,
    presenze: bool = False,
    lingua: str = "it",
) -> tuple[discord.Embed, discord.File | None]:
    """Embed (e grafico) di /utility serverstats per la vista scelta."""
    v = await costruisci_vista(guild, vista, giorni, metrica, ruolo, utente, visti_da, canale, presenze, lingua)
    return v.embed, (discord.File(io.BytesIO(v.png), filename="statistiche.png") if v.png else None)


class _PeriodoView(BaseView):
    """Bottoni sotto la risposta: cambia periodo o aggiorna. Li usa solo chi ha lanciato il comando."""

    def __init__(self, autore_id: int, guild, vista, giorni, metrica, ruolo, utente, visti_da=None,
                 canale=None, presenze: bool = False, lingua: str = "it") -> None:
        super().__init__(timeout=300)
        self._autore_id = autore_id
        self._visti_da = visti_da
        self._args = [guild, vista, metrica, ruolo, utente]
        self._extra = {"canale": canale, "presenze": presenze, "lingua": lingua}
        self.giorni = giorni
        for periodo in PERIODI_BOTTONI:
            b = discord.ui.Button(
                label=f"{periodo} giorni",
                style=discord.ButtonStyle.primary if periodo == giorni else discord.ButtonStyle.secondary,
            )
            b.callback = self._cambia(periodo)
            self.add_item(b)
        agg = discord.ui.Button(label="Aggiorna", emoji="🔄", style=discord.ButtonStyle.secondary)
        agg.callback = self._cambia(None)
        self.add_item(agg)

    def _cambia(self, periodo):
        async def _callback(interaction: discord.Interaction) -> None:
            if interaction.user.id != self._autore_id:
                await interaction.response.send_message(await testo_per(interaction, "serverstats_questi_bottoni_sono_di_chi"), ephemeral=True)
                return
            await interaction.response.defer()
            giorni = periodo or self.giorni
            guild, vista, metrica, ruolo, utente = self._args
            embed, file = await costruisci_statistiche(guild, vista, giorni, metrica, ruolo, utente, self._visti_da, **self._extra)
            nuova = _PeriodoView(self._autore_id, guild, vista, giorni, metrica, ruolo, utente, self._visti_da, **self._extra)
            await interaction.edit_original_response(
                embed=embed, attachments=[file] if file else [], view=nuova, allowed_mentions=_NESSUNA_MENZIONE
            )

        return _callback


async def _consenti(interaction: discord.Interaction) -> bool:
    """Modulo acceso e, se l'admin ha scelto dei ruoli, solo per loro (STA-013). Risponde da sé se rifiuta."""
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
        return False
    if not await db.is_module_active_for_guild(guild.id, MODULE_SERVER_STATS):
        await interaction.response.send_message(await testo_per(interaction, "ping_questo_modulo_non_attivo_su"), ephemeral=True)
        return False
    imp = await activity_stats_repo.get_settings(guild.id)
    if not puo_vedere(interaction.user, imp.view_roles):
        await interaction.response.send_message(await testo_per(interaction, "serverstats_non_puoi_vedere"), ephemeral=True)
        return False
    return True


NOME_MENU_MEMBRO = "Statistiche del membro"
NOME_MENU_CANALE = "Statistiche del canale"
GIORNI_MENU = 30


class ServerStatsCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # STA-011: i menu col tasto destro (Discord ha solo menu sull'utente e sul messaggio: quello del canale
        # si apre sul messaggio e mostra il canale che lo contiene)
        self._menu_membro = app_commands.ContextMenu(
            name=NOME_MENU_MEMBRO, callback=self.menu_membro, type=discord.AppCommandType.user,
            allowed_contexts=app_commands.AppCommandContext(guild=True, dm_channel=False, private_channel=False),
        )
        self._menu_canale = app_commands.ContextMenu(
            name=NOME_MENU_CANALE, callback=self.menu_canale, type=discord.AppCommandType.message,
            allowed_contexts=app_commands.AppCommandContext(guild=True, dm_channel=False, private_channel=False),
        )

    async def cog_load(self) -> None:
        await super().cog_load()
        self.bot.tree.add_command(self._menu_membro)
        self.bot.tree.add_command(self._menu_canale)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(NOME_MENU_MEMBRO, type=discord.AppCommandType.user)
        self.bot.tree.remove_command(NOME_MENU_CANALE, type=discord.AppCommandType.message)
        await super().cog_unload()

    def _presenze(self) -> bool:
        return bool(getattr(getattr(self.bot, "intents", None), "presences", False))

    async def _rispondi(self, interaction, vista, giorni, metrica="messages", ruolo=None, utente=None, canale=None, effimera=False) -> None:
        lingua = await lingua_interazione(interaction)
        embed, file = await costruisci_statistiche(
            interaction.guild, vista, giorni, metrica, ruolo, utente, interaction.user, canale, self._presenze(), lingua
        )
        view = _PeriodoView(interaction.user.id, interaction.guild, vista, giorni, metrica, ruolo, utente,
                            interaction.user, canale, self._presenze(), lingua)
        kwargs = {"embed": embed, "view": view, "allowed_mentions": _NESSUNA_MENZIONE}
        if file is not None:
            kwargs["file"] = file
        await interaction.followup.send(ephemeral=effimera, **kwargs)

    async def menu_membro(self, interaction: discord.Interaction, membro: discord.Member) -> None:
        if not await _consenti(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        await self._rispondi(interaction, "membro", GIORNI_MENU, utente=membro, effimera=True)

    async def menu_canale(self, interaction: discord.Interaction, messaggio: discord.Message) -> None:
        if not await _consenti(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        canale = messaggio.channel
        if not isinstance(canale, discord.abc.GuildChannel):  # un thread: si guarda il suo canale
            canale = getattr(canale, "parent", None) or canale
        await self._rispondi(interaction, "canale", GIORNI_MENU, canale=canale, effimera=True)

    @comando_di_gruppo(
        "utility",
        nome="serverstats",
        descrizione="Statistiche del server: crescita, attività dei canali e dei membri.",
    )
    @app_commands.describe(
        days="Quanti giorni indietro (default 14, massimo 90)",
        vista="Cosa mostrare (default: crescita)",
        metrica="Messaggi o minuti in vocale (per le viste di attività)",
        ruolo="Limita la classifica ai membri con questo ruolo, o conta chi lo ha",
        utente="Il membro, per la vista «Attività di un membro» (vuoto: tu)",
        canale="Il canale, per la vista «Attività di un canale»",
        formato="Grafico (predefinito) o file CSV con i numeri",
    )
    @app_commands.choices(
        vista=[app_commands.Choice(name=nome, value=chiave) for chiave, nome in VISTE.items()],
        metrica=[
            app_commands.Choice(name="Messaggi", value="messages"),
            app_commands.Choice(name="Minuti in vocale", value="voice_minutes"),
            app_commands.Choice(name="Comandi usati", value="comandi"),
        ],
        formato=[app_commands.Choice(name="Grafico", value="grafico"), app_commands.Choice(name="File CSV", value="csv")],
    )
    async def server_stats(
        self,
        interaction: discord.Interaction,
        days: app_commands.Range[int, 1, 90] = DEFAULT_DAYS,
        vista: app_commands.Choice[str] | None = None,
        metrica: app_commands.Choice[str] | None = None,
        ruolo: discord.Role | None = None,
        utente: discord.Member | None = None,
        canale: discord.abc.GuildChannel | None = None,
        formato: app_commands.Choice[str] | None = None,
    ) -> None:
        if not await _consenti(interaction):
            return
        guild = interaction.guild
        await interaction.response.defer()
        chiave = vista.value if vista is not None else "crescita"
        misura = metrica.value if metrica is not None else "messages"
        if formato is not None and formato.value == "csv":  # STA-056
            lingua = await lingua_interazione(interaction)
            v = await costruisci_vista(guild, chiave, days, misura, ruolo, utente, interaction.user, canale, self._presenze(), lingua)
            if not v.righe:
                await interaction.followup.send(await testo_per(interaction, "serverstats_csv_senza_tabella"), ephemeral=True)
                return
            dati = tabella_in_csv(v.intestazione, v.righe)
            await interaction.followup.send(
                embed=v.embed, file=discord.File(io.BytesIO(dati), filename=f"statistiche-{chiave}.csv"), allowed_mentions=_NESSUNA_MENZIONE
            )
            return
        await self._rispondi(interaction, chiave, days, misura, ruolo, utente, canale)


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_SERVER_STATS,
            display_name="Server Stats",
            category="utility",
            description="Statistiche del server: crescita, attività di canali e membri, ruoli per attività.",
            premium_capable=False,
        )
    )
    await bot.add_cog(ServerStatsCog(bot))
