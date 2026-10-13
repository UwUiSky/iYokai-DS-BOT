"""
cogs/leveling/leveling.py
============================
XP testuale (on_message) e vocale (task periodico ogni 60s), livelli,
economia (daily/work/pay/balance, shop, drop, giveaway), cassa del
server, gilde/clan, classifiche mensili e di sempre, impostazioni dei
livelli. Modulo sempre gratuito.
Funzioni coperte: SPEC §15, §22.14, §23.6

Message Content Intent: è attivo (vedi main.py). L'XP però non guarda
mai il testo: gli basta sapere CHE un messaggio è stato inviato.

L'XP vocale usa un task periodico (tasks.loop) e non l'evento
on_voice_state_update: l'XP si accumula minuto per minuto per tutta
la permanenza in vocale, non solo quando si entra o si esce.
"""

from __future__ import annotations

import io
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands, tasks

from core.command_access import Livello, richiedi
from core.command_groups import CogConGruppi, comando_di_gruppo, togli_comandi_del_cog
from core.database import db
from core.role_safety import check_role_assignable
from core.repositories.blacklist_repo import blacklist_repo
from core.repositories.leveling_repo import leveling_repo
from core.repositories.level_reward_repo import level_reward_repo
from core.repositories.leveling_settings_repo import (
    RegolaPiena,
    leveling_settings_repo,
)
from core.monthly_winners_logic import MEDALS, previous_period_key
# I due aiuti con il trattino servono al bottone degli inviti in gilda:
# un bottone "dinamico" non passa dalla BaseView, quindi il controllo
# blacklist e la risposta agli errori vanno chiamati a mano.
from core.ui_base import BaseView, _rispondi_con_errore, _utente_o_server_in_blacklist
from cogs.leveling._pagine import invia_lista, taglia
from core.repositories.monthly_winners_repo import monthly_winners_repo
from core.clan_leaderboard_logic import previous_period_key as clan_previous_period_key
from core.repositories.clan_leaderboard_config_repo import clan_leaderboard_config_repo
from core.repositories.shop_repo import EsitoAcquisto, shop_repo
from core.rank_card_image import COLORE_DI_BASE, TEMA_DI_BASE, DatiRankCard, render_rank_card
from core.safe_image import run_image_task
from core.drop_logic import DEFAULT_MAX_COINS, DEFAULT_MIN_COINS, should_trigger_drop
from core.giveaway_logic import (
    MAX_INGRESSI_EXTRA,
    MAX_MESSAGGI_RICHIESTI,
    MAX_PREMIO_GIVEAWAY,
    biglietti_di,
    descrizione_giveaway,
    requisiti_mancanti,
    titolo_giveaway,
)
from core.repositories.giveaway_repo import ModelloPieno, giveaway_repo
from core.premium_pricing_logic import TIER_MONTHS_REQUIRED
from core.premium_purchase_service import PurchaseOutcome, purchase_premium_tier
from core.repositories.guild_chest_repo import (
    REASON_EVENT_LOBBY_PRIZE,
    REASON_EVENT_WINNER_PRIZE,
    guild_chest_repo,
)
from core.guild_clan_logic import (
    CREATION_DEFICIT,
    CREATION_GRACE_HOURS,
    MAX_ADMINS_PER_CLAN,
    MAX_MODS_PER_CLAN,
    TAG_MAX_LENGTH,
    TAG_MIN_LENGTH,
    is_creation_deficit_covered,
    next_channel_unlock_cost,
    next_channel_voice_hours_requirement,
    validate_guild_tag,
    voice_ticks_to_hours,
)
from core.repositories.guild_clan_repo import (
    EsitoIngresso,
    EsitoRuolo,
    ROLE_ADMIN,
    ROLE_CO_OWNER,
    ROLE_MEMBER,
    ROLE_MOD,
    ROLE_OWNER,
    guild_clan_repo,
)
from core.guild_clan_role_service import (
    clear_clan_officers_presence,
    clear_member_clan_presence,
    sync_member_clan_role,
)
from core.guild_clan_boost_logic import (
    BOOST_DURATION_HOURS,
    BOOST_MULTIPLIER,
    GUILD_BOOST_COSTS,
    INDIVIDUAL_BOOST_COSTS,
    Beneficio,
    StatoBoost,
    TipoBoost,
    benefici_attivi,
    tipi_acquistabili,
)
from core.leveling_logic import (
    ConfigLivelli,
    DAILY_COOLDOWN_SECONDS,
    FATTORE_MASSIMO,
    FATTORE_MINIMO,
    LIMITI_IMPOSTAZIONI,
    LevelingSettings,
    MAX_REGOLE_PER_TIPO,
    colore_valido,
    id_canali_per_le_regole,
    deve_annunciare,
    scegli_premi,
    xp_con_moltiplicatore,
    WORK_COOLDOWN_SECONDS,
    is_eligible_for_voice_xp,
    period_key,
    seconds_until_next_claim,
    xp_for_level,
)
from core.premium import PremiumModule, registry

logger = logging.getLogger("iyokai.leveling")

MODULE_LEVELING = "leveling"

# Solo questi tipi di messaggio danno XP: quelli scritti da una persona.
TIPI_DI_MESSAGGIO_CON_XP = (discord.MessageType.default, discord.MessageType.reply)


# Limite di Discord per il motivo scritto nel registro di controllo.
LIMITE_MOTIVO = 512

# Chi può gestire la gilda: invitare, espellere, comprare canali e boost.
RUOLI_UFFICIALI = (ROLE_OWNER, ROLE_CO_OWNER, ROLE_ADMIN)

# LIM-18: lunghezza massima dei testi liberi e dei titoli degli embed.
MAX_NOME_CLAN = 64
MAX_NOME_OGGETTO = 80
MAX_DESCRIZIONE_OGGETTO = 200
MAX_NOME_CANALE = 100
LIMITE_TITOLO_EMBED = 256
LIMITE_RIGA_NEGOZIO = 380
RUOLI_PREMIO_PER_PAGINA = 20
MEMBRI_PER_PAGINA = 20


async def _comando_rifiutato(interaction: discord.Interaction) -> bool:
    """
    Controllo comune, prima riga di ogni comando di questo cog (M 9.7).
    True se il comando non va eseguito, dopo aver già avvisato l'utente:
    fuori da un server, oppure con il modulo "leveling" spento su questo
    server. Il test tests/test_leveling_modulo_spento.py passa in
    rassegna tutti i comandi: uno nuovo senza questa riga lo fa fallire.
    """
    if interaction.guild is None:
        await interaction.response.send_message(
            "Questo comando è disponibile solo dentro un server.", ephemeral=True
        )
        return True
    if await db.is_module_active_for_guild(interaction.guild.id, MODULE_LEVELING):
        return False
    await interaction.response.send_message(
        "Questo modulo non è attivo su questo server. "
        "Un amministratore può attivarlo con `/admin setup attiva`.",
        ephemeral=True,
    )
    return True


# Storico della tesoreria in /clan info: quante righe e come chiamarle.
MOVIMENTI_IN_CLAN_INFO = 5
NOMI_DEI_MOVIMENTI = {
    "donation": "donazione",
    "creation_deficit": "deficit di creazione",
    "channel_unlock": "canale extra",
    "channel_unlock_refund": "rimborso canale extra",
    "monthly_decay": "decadimento mensile",
    "treasury_transfer_in": "trasferimento in entrata",
    "treasury_transfer_out": "trasferimento in uscita",
    "guild_boost": "boost di gilda",
}


def _scelte_boost(prezzi: dict) -> list[app_commands.Choice[str]]:
    """Le tre scelte fisse dell'opzione `tipo` di /clan boost (D23)."""
    return [
        app_commands.Choice(
            name=f"Exp: ×{BOOST_MULTIPLIER} ai punti esperienza ({prezzi[TipoBoost.EXP]} coin)",
            value=TipoBoost.EXP.value,
        ),
        app_commands.Choice(
            name=f"Coin: ×{BOOST_MULTIPLIER} alle coin ({prezzi[TipoBoost.COIN]} coin)",
            value=TipoBoost.COIN.value,
        ),
        app_commands.Choice(
            name=f"Super: exp e coin insieme ({prezzi[TipoBoost.SUPER]} coin)",
            value=TipoBoost.SUPER.value,
        ),
    ]


def _tipo_da_scelta(scelta) -> TipoBoost:
    return TipoBoost(getattr(scelta, "value", scelta))


def _righe_boost_attivi(attivi: dict) -> list[str]:
    """Una riga per boost attivo: il super (stessa scadenza su exp e
    coin) vale una riga sola."""
    if not attivi:
        return []
    exp, coin = attivi.get(Beneficio.EXP), attivi.get(Beneficio.COIN)
    if exp is not None and exp == coin:
        return [f"✨ Super (exp e coin) ×{BOOST_MULTIPLIER} fino a <t:{int(exp.timestamp())}:R>"]
    nomi = {Beneficio.EXP: "Exp", Beneficio.COIN: "Coin"}
    return [
        f"✨ {nomi[b]} ×{BOOST_MULTIPLIER} fino a <t:{int(scad.timestamp())}:R>"
        for b, scad in attivi.items()
    ]


def _testo_boost_gia_attivo(attivi, scad_exp, scad_coin, now, soggetto: str) -> str:
    """Messaggio preciso quando un boost è rifiutato perché già attivo."""
    attivi = dict(attivi)
    exp, coin = attivi.get(Beneficio.EXP), attivi.get(Beneficio.COIN)
    if exp is not None and exp == coin:
        descrizione = f"il boost super attivo fino a <t:{int(exp.timestamp())}:R>"
    else:
        pezzi = [
            f"il boost {b.value} attivo fino a <t:{int(scad.timestamp())}:R>"
            for b, scad in attivi.items()
        ]
        descrizione = " e ".join(pezzi)
    possibili = [
        t.value for t in tipi_acquistabili(scad_exp, scad_coin, now)
        if t is not TipoBoost.SUPER
    ] if len(attivi) == 1 else []
    if possibili:
        coda = f"puoi comprare solo il boost {possibili[0]}."
    else:
        coda = "non puoi comprare altri boost finché quelli attivi non scadono."
    return f"{soggetto} già {descrizione}: {coda}"


def _riga_movimento(movimento) -> str:
    """Una riga dello storico: data, importo con il segno, causale, autore."""
    segno = "+" if movimento.amount > 0 else ""
    causale = NOMI_DEI_MOVIMENTI.get(movimento.reason, movimento.reason)
    autore = f" — <@{movimento.user_id}>" if movimento.user_id is not None else ""
    return f"<t:{int(movimento.created_at.timestamp())}:d> {segno}{movimento.amount} {causale}{autore}"


def _format_seconds(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    remaining_minutes = minutes % 60
    return f"{hours}h {remaining_minutes}m"


# Per quanto resta valido un invito in gilda.
VALIDITA_INVITO_ORE = 24


class BottoneInvitoClan(
    discord.ui.DynamicItem[discord.ui.Button],
    template=(
        r"clan_invito:(?P<azione>accetta|rifiuta):"
        r"(?P<clan_id>\d+):(?P<user_id>\d+):(?P<scadenza>\d+)"
    ),
):
    """
    Bottone "Accetta" o "Rifiuta" di un invito in gilda (M 9.8). Gilda,
    invitato e scadenza stanno nel custom_id: dopo un riavvio del bot
    discord.py ricostruisce il bottone da lì, senza una tabella degli
    inviti. Va registrato all'avvio con bot.add_dynamic_items (setup).
    L'invito non scrive nulla: nella gilda si entra solo accettando.
    """

    def __init__(self, azione: str, clan_id: int, user_id: int, scadenza: int) -> None:
        accetta = azione == "accetta"
        super().__init__(
            discord.ui.Button(
                label="Accetta" if accetta else "Rifiuta",
                style=discord.ButtonStyle.success if accetta else discord.ButtonStyle.secondary,
                custom_id=f"clan_invito:{azione}:{clan_id}:{user_id}:{scadenza}",
            )
        )
        self.azione = azione
        self.clan_id = clan_id
        self.user_id = user_id
        self.scadenza = scadenza

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(
            match["azione"], int(match["clan_id"]), int(match["user_id"]), int(match["scadenza"])
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        # SEC-10: un bottone dinamico non ha una BaseView sopra di sé,
        # quindi il controllo blacklist si fa qui.
        if await _utente_o_server_in_blacklist(interaction):
            return False
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "Questo invito non è per te.", ephemeral=True
            )
            return False
        return True

    async def callback(self, interaction: discord.Interaction) -> None:
        try:
            await self._rispondi(interaction)
        except Exception:
            logger.exception("Errore nel bottone di un invito in gilda")
            await _rispondi_con_errore(interaction)

    async def _rispondi(self, interaction: discord.Interaction) -> None:
        if datetime.now(timezone.utc).timestamp() > self.scadenza:
            await interaction.response.edit_message(
                content="⌛ Questo invito è scaduto.", view=None
            )
            return
        if self.azione == "rifiuta":
            await interaction.response.edit_message(
                content=f"{interaction.user.mention} ha rifiutato l'invito.", view=None
            )
            return

        esito = await guild_clan_repo.add_member(self.clan_id, interaction.user.id)
        if esito == EsitoIngresso.GILDA_INESISTENTE:
            await interaction.response.edit_message(
                content="Questa gilda non esiste più.", view=None
            )
            return
        if esito == EsitoIngresso.GIA_IN_UNA_GILDA:
            await interaction.response.send_message(
                "Fai già parte di una gilda in questo server: per accettare lasciala prima "
                "con `/clan lascia`.",
                ephemeral=True,
            )
            return
        if esito == EsitoIngresso.GILDA_PIENA:
            await interaction.response.send_message(
                "La gilda è al completo: riprova quando si libera un posto.", ephemeral=True
            )
            return

        guild = interaction.guild
        clan = await guild_clan_repo.get_member_clan_in_guild(guild.id, interaction.user.id)
        nome = taglia(clan.name, MAX_NOME_CLAN) if clan is not None else "la gilda"
        # Prima la risposta (entro 3 secondi), poi ruoli e permessi.
        await interaction.response.edit_message(
            content=f"✅ {interaction.user.mention} è entrato in **{nome}**.", view=None
        )
        if clan is not None:
            categoria = guild.get_channel(clan.category_id) if clan.category_id is not None else None
            await sync_member_clan_role(guild, categoria, interaction.user, ROLE_MEMBER)


_SG_ECONOMIA = ("economia", "Economia: negozio, cassa, premi, giveaway e vincitori del mese")
_SG_RUOLI = ("ruoli", "Ruoli: ruoli-premio per livello e menu di ruoli")
_SG_SHOP = ("shop", "Negozio: spendi i tuoi coin su oggetti o ruoli.")
_SG_BACHECA = ("bacheca", "Annuncio automatico della top 3 gilde a fine mese.")
_SG_TESORERIA = ("tesoreria", "Tesoreria della tua gilda.")
_SG_IMPOSTAZIONI = ("impostazioni", "Impostazioni dei livelli: XP, annunci, ruoli-premio, esclusioni.")

_SCELTE_AZIONE_XP = [
    app_commands.Choice(name="Aggiungi XP", value="aggiungi"),
    app_commands.Choice(name="Togli XP", value="togli"),
    app_commands.Choice(name="Imposta il livello", value="livello"),
    app_commands.Choice(name="Imposta gli XP dentro il livello", value="xp_nel_livello"),
    app_commands.Choice(name="Azzera XP e livello", value="azzera"),
]
_SCELTE_AZIONE_MONETE = [
    app_commands.Choice(name="Aggiungi coin", value="aggiungi"),
    app_commands.Choice(name="Togli coin", value="togli"),
    app_commands.Choice(name="Imposta il saldo", value="imposta"),
    app_commands.Choice(name="Azzera il saldo", value="azzera"),
]

_SCELTE_AZIONE_MODELLO = [
    app_commands.Choice(name="Salva (o aggiorna)", value="salva"),
    app_commands.Choice(name="Elenca", value="elenco"),
    app_commands.Choice(name="Elimina", value="elimina"),
    app_commands.Choice(name="Avvia un giveaway dal modello", value="avvia"),
]

_SCELTE_ANNUNCIO = [
    app_commands.Choice(name="Spento", value="spento"),
    app_commands.Choice(name="Nel canale in cui scrive", value="canale_corrente"),
    app_commands.Choice(name="Messaggio privato", value="dm"),
    app_commands.Choice(name="In un canale scelto", value="canale_scelto"),
]
_SCELTE_PREMI = [
    app_commands.Choice(name="Accumula (tieni tutti i ruoli)", value="accumula"),
    app_commands.Choice(name="Sostituisci (togli i precedenti)", value="sostituisci"),
]
_SCELTE_MOLTIPLICATORI = [
    app_commands.Choice(name="Si sommano", value="somma"),
    app_commands.Choice(name="Vale solo il più alto", value="massimo"),
]
_SCELTE_TEMA = [
    app_commands.Choice(name="Scuro", value="scuro"),
    app_commands.Choice(name="Chiaro", value="chiaro"),
    app_commands.Choice(name="Notte", value="notte"),
]
_NOMI_ANNUNCIO = {c.value: c.name for c in _SCELTE_ANNUNCIO}
_NOMI_PREMI = {c.value: c.name for c in _SCELTE_PREMI}
_NOMI_MOLTIPLICATORI = {c.value: c.name for c in _SCELTE_MOLTIPLICATORI}


def _embed_impostazioni(config: ConfigLivelli) -> discord.Embed:
    """Riepilogo delle impostazioni dei livelli (entra nei limiti degli embed)."""
    i = config.impostazioni
    annuncio = _NOMI_ANNUNCIO[i.levelup_mode]
    if i.levelup_mode == "canale_scelto" and i.levelup_channel_id:
        annuncio += f" (<#{i.levelup_channel_id}>)"
    filtri = []
    if i.levelup_min_level:
        filtri.append(f"dal livello {i.levelup_min_level}")
    if i.levelup_every > 1:
        filtri.append(f"ogni {i.levelup_every} livelli")
    if i.levelup_only_rewards:
        filtri.append("solo con ruolo-premio")
    embed = discord.Embed(title="Impostazioni dei livelli", color=discord.Color.blurple())
    embed.add_field(
        name="XP e coin",
        value=(
            f"Messaggio: **{i.text_xp}** XP, ogni **{i.text_cooldown_seconds}** s\n"
            f"Vocale: **{i.voice_xp_per_minute}** XP e **{i.voice_coins_per_minute}** coin al minuto\n"
            f"Daily: **{i.daily_coins}** coin · Work: **{i.work_min}-{i.work_max}** coin\n"
            f"Livello massimo: **{i.max_level or 'nessun tetto'}**"
        ),
        inline=False,
    )
    embed.add_field(
        name="Annuncio level-up",
        value=annuncio + (f" — {', '.join(filtri)}" if filtri else ""),
        inline=False,
    )
    embed.add_field(name="Ruoli-premio", value=_NOMI_PREMI[i.reward_mode], inline=True)
    embed.add_field(name="Moltiplicatori", value=_NOMI_MOLTIPLICATORI[i.multiplier_mode], inline=True)

    def elenco(righe: list[str]) -> str:
        if not righe:
            return "nessuno"
        testo = ", ".join(righe[:15])
        return testo + (f" e altri {len(righe) - 15}" if len(righe) > 15 else "")

    embed.add_field(
        name="Senza XP",
        value=elenco([f"<#{c}>" for c in sorted(config.canali_esclusi)]
                     + [f"<@&{r}>" for r in sorted(config.ruoli_esclusi)]),
        inline=False,
    )
    embed.add_field(
        name="Moltiplicatori attivi",
        value=elenco([f"<#{c}> ×{f:g}" for c, f in sorted(config.mult_canali.items())]
                     + [f"<@&{r}> ×{f:g}" for r, f in sorted(config.mult_ruoli.items())]),
        inline=False,
    )
    return embed
_SG_BOOST = ("boost", "Boost XP/coin del Sistema Gilde/Clan.")


class LevelingCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._voice_xp_tick.start()

    def cog_unload(self) -> None:
        self._voice_xp_tick.cancel()
        togli_comandi_del_cog(self)

    # ================================================================
    # XP testuale
    # ================================================================
    async def _config(self, guild_id: int) -> ConfigLivelli:
        """
        Le impostazioni dei livelli del server. Se il database non risponde
        valgono i valori di sempre: un guasto qui non deve fermare l'XP.
        """
        try:
            return await leveling_settings_repo.get_config(guild_id)
        except Exception:
            logger.warning("Impostazioni dei livelli non lette per %s: uso quelle di base.", guild_id)
            return ConfigLivelli()

    async def _annuncia_level_up(
        self,
        member: discord.Member,
        guild: discord.Guild,
        canale_corrente,
        new_level: int,
        impostazioni: LevelingSettings,
        livello_precedente: int | None = None,
    ) -> None:
        """
        Dice del level-up dove ha scelto il server (spento, canale in cui
        è successo, DM, canale scelto). Un errore di Discord non ferma mai
        l'assegnazione dei ruoli.
        """
        ha_premio = False
        if impostazioni.levelup_only_rewards:
            premi = await level_reward_repo.get_rewards_up_to_level(guild.id, new_level)
            # Con un salto di più livelli conta il premio di qualunque livello saltato.
            prima = new_level - 1 if livello_precedente is None else min(livello_precedente, new_level - 1)
            ha_premio = any(prima < r.level_threshold <= new_level for r in premi)
        if not deve_annunciare(new_level, impostazioni, ha_premio, livello_precedente):
            return

        testo = f"🎉 {member.mention} è salito al livello **{new_level}**!"
        if impostazioni.levelup_mode == "dm":
            destinazione = member
        elif impostazioni.levelup_mode == "canale_scelto":
            destinazione = guild.get_channel(impostazioni.levelup_channel_id or 0)
        else:
            destinazione = canale_corrente
        if destinazione is None:
            return
        try:
            await destinazione.send(testo)
        except discord.HTTPException:
            pass

    async def _grant_level_rewards(
        self,
        member: discord.Member,
        guild: discord.Guild,
        new_level: int,
        modo: str = "accumula",
        togli_superiori: bool = False,
    ) -> None:
        """
        Condiviso tra XP testuale e vocale (SPEC.md §15.13) — un
        solo punto che assegna i ruoli-premio, non due copie della
        stessa logica. Salta i ruoli che il membro ha già (un
        re-invio ripetuto non deve fallire né generare richieste
        Discord inutili).

        `modo` (NF-15): "accumula" tiene tutti i ruoli dei livelli
        raggiunti; "sostituisci" dà solo quello del livello più alto e
        toglie gli altri ruoli-premio.

        SEC-4/SEC-17: l'assegnazione è automatica (self_service=True),
        quindi ogni ruolo viene ricontrollato con check_role_assignable
        prima di assegnarlo — il ruolo può aver preso permessi
        pericolosi dopo la configurazione del ruolo-premio.
        """
        ricompense = await level_reward_repo.get_rewards_up_to_level(guild.id, new_level)
        non_piu_raggiunti = []
        if togli_superiori:
            non_piu_raggiunti = [
                r.role_id
                for r in await level_reward_repo.list_rewards(guild.id)
                if r.level_threshold > new_level
            ]
        if not ricompense and not non_piu_raggiunti:
            return

        id_da_dare, id_da_togliere = scegli_premi(ricompense, modo)
        id_ruoli_posseduti = {ruolo.id for ruolo in member.roles}
        da_assegnare = []
        for role_id in id_da_dare:
            if role_id in id_ruoli_posseduti:
                continue
            ruolo = guild.get_role(role_id)
            if ruolo is None:
                continue
            if check_role_assignable(guild, ruolo, guild.me, self_service=True) is not None:
                continue
            da_assegnare.append(ruolo)

        da_togliere = []
        for role_id in id_da_togliere:
            if role_id not in id_ruoli_posseduti:
                continue
            ruolo = guild.get_role(role_id)
            # Si tolgono solo i ruoli che il bot può gestire (gerarchia).
            if ruolo is None or ruolo.managed or ruolo.position >= guild.me.top_role.position:
                continue
            da_togliere.append(ruolo)

        da_togliere_sempre = []
        for role_id in non_piu_raggiunti:
            ruolo = guild.get_role(role_id) if role_id in id_ruoli_posseduti else None
            if ruolo is None or ruolo.managed or ruolo.position >= guild.me.top_role.position:
                continue
            da_togliere_sempre.append(ruolo)

        # "Sostituisci": i vecchi ruoli si tolgono SOLO se il nuovo è arrivato
        # (o c'era già). Un ruolo nuovo non assegnabile non lascia il membro
        # senza nessun ruolo-premio.
        nuovo_assicurato = all(
            r in id_ruoli_posseduti or r in {x.id for x in da_assegnare} for r in id_da_dare
        )
        try:
            if da_assegnare:
                await member.add_roles(
                    *da_assegnare, reason=f"Ruolo-premio per aver raggiunto il livello {new_level}"
                )
            if da_togliere and nuovo_assicurato:
                await member.remove_roles(
                    *da_togliere, reason=f"Ruolo-premio sostituito al livello {new_level}"
                )
            if da_togliere_sempre:
                await member.remove_roles(
                    *da_togliere_sempre,
                    reason=f"Livello sceso a {new_level}: ruolo-premio non più raggiunto",
                )
        except discord.HTTPException:
            logger.warning(
                "Impossibile aggiornare i ruoli-premio di %s nel server %s.", member.id, guild.id
            )

    class DropClaimView(BaseView):
        """
        "Primo che clicca vince" — self.claimed_by è lo stato
        condiviso in memoria per QUESTO drop specifico (un'istanza
        per drop, non persistita: se il bot si riavvia mentre un
        drop è ancora aperto, va semplicemente perso, accettabile
        per una piccola sorpresa occasionale).
        """

        def __init__(self, guild_id: int, amount: int) -> None:
            super().__init__(timeout=120)
            self.guild_id = guild_id
            self.amount = amount
            self.claimed_by: int | None = None

        @discord.ui.button(label="Raccogli", emoji="💰", style=discord.ButtonStyle.success)
        async def raccogli(
            self, interaction: discord.Interaction, button: discord.ui.Button
        ) -> None:
            # BUG-17: nessun await tra controllo e assegnazione: è atomico.
            if self.claimed_by is not None:
                await interaction.response.send_message(
                    "Questo drop è già stato raccolto.", ephemeral=True
                )
                return

            self.claimed_by = interaction.user.id
            await leveling_repo.add_coins(self.guild_id, interaction.user.id, self.amount)

            button.disabled = True
            button.label = f"Raccolto da {interaction.user.display_name}"
            await interaction.response.edit_message(view=self)

    async def _xp_testuale(
        self, message: discord.Message, config: ConfigLivelli, id_ruoli: list[int], id_canale: list[int]
    ) -> None:
        # Chi è escluso (canale, categoria o ruolo) non dà XP nemmeno alla
        # gilda: questo metodo non viene chiamato (vedi on_message).
        impostazioni = config.impostazioni
        clan = await guild_clan_repo.get_member_clan_in_guild(message.guild.id, message.author.id)
        if clan is not None and clan.officialized:
            # Lato TESTUALE del guadagno ×2 di gilda (SPEC.md
            # §15.14) — indipendente dall'XP personale sotto: stesso
            # cooldown del testo normale, nessuna coin, nessun boost
            # (scoped al solo vocale, Fase 54). Un fallimento qui non
            # deve mai impedire l'XP personale.
            await guild_clan_repo.apply_text_tick(clan.id, message.author.id)

        importo = xp_con_moltiplicatore(
            impostazioni.text_xp, config.moltiplicatore(id_canale, id_ruoli)
        )
        risultato = await leveling_repo.add_text_xp(
            message.guild.id,
            message.author.id,
            amount=importo,
            cooldown_seconds=impostazioni.text_cooldown_seconds,
            max_level=impostazioni.max_level,
        )
        if risultato.granted and risultato.leveled_up:
            await self._annuncia_level_up(
                message.author, message.guild, message.channel, risultato.new_level,
                impostazioni, risultato.previous_level,
            )
            await self._grant_level_rewards(
                message.author, message.guild, risultato.new_level, impostazioni.reward_mode
            )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        # I messaggi di sistema (boost, messaggio fissato, benvenuto
        # automatico) hanno un autore vero ma non li ha scritti lui.
        if message.type not in TIPI_DI_MESSAGGIO_CON_XP:
            return

        # SEC-10: un utente in blacklist non deve continuare a
        # guadagnare XP/coin scrivendo messaggi.
        if await blacklist_repo.is_user_blacklisted(message.author.id):
            return

        if not await db.is_module_active_for_guild(message.guild.id, MODULE_LEVELING):
            return

        # NF-28: i messaggi contano per i giveaway che chiedono un minimo.
        try:
            await giveaway_repo.count_message(message.guild.id, message.author.id)
        except Exception:
            logger.warning("Messaggi dei giveaway non contati nel server %s.", message.guild.id)

        config = await self._config(message.guild.id)
        id_ruoli = [r.id for r in getattr(message.author, "roles", [])]
        # NF-15: canali e ruoli senza XP. Il drop sotto resta indipendente.
        # Un thread o un post di forum vale come il suo canale di origine.
        id_canale = id_canali_per_le_regole(message.channel)
        if not config.e_escluso(id_canale, id_ruoli):
            await self._xp_testuale(message, config, id_ruoli, id_canale)

        if should_trigger_drop(random.random()):
            importo = random.randint(DEFAULT_MIN_COINS, DEFAULT_MAX_COINS)
            view = self.DropClaimView(message.guild.id, importo)
            try:
                await message.channel.send(
                    f"💰 È apparso un drop di **{importo}** coin! Clicca per raccoglierlo.",
                    view=view,
                )
            except discord.HTTPException:
                pass

    # ================================================================
    # XP vocale — task periodico
    # ================================================================
    @tasks.loop(seconds=60)
    async def _voice_xp_tick(self) -> None:
        for guild in self.bot.guilds:
            try:
                if not await db.is_module_active_for_guild(guild.id, MODULE_LEVELING):
                    continue
                await self._process_guild_voice_xp(guild)
            except Exception:
                # Un errore in UN server non deve interrompere il
                # giro per tutti gli altri.
                logger.exception(
                    "Errore nel calcolo XP vocale per il server %s", guild.id
                )

    @_voice_xp_tick.before_loop
    async def _before_voice_xp_tick(self) -> None:
        await self.bot.wait_until_ready()

    async def _process_guild_voice_xp(self, guild: discord.Guild) -> None:
        afk_channel_id = guild.afk_channel.id if guild.afk_channel else None

        # PERF-4: si raccolgono tutti i presenti del server e si scrive in
        # una volta sola (una query per la blacklist, una transazione per
        # l'XP), non una transazione per ogni persona.
        config = await self._config(guild.id)
        presenti: list[tuple[discord.Member, discord.VoiceChannel, bool]] = []
        moltiplicatori: dict[int, float] = {}
        for channel in guild.voice_channels:
            members = [m for m in channel.members if not m.bot]
            if not members:
                continue

            is_afk = channel.id == afk_channel_id
            for member in members:
                others_not_muted = sum(
                    1
                    for other in members
                    if other.id != member.id and not other.voice.self_mute
                )
                eligible = is_eligible_for_voice_xp(
                    is_self_deaf=member.voice.self_deaf,
                    is_afk_channel=is_afk,
                    other_members_not_self_muted=others_not_muted,
                )
                id_ruoli = [r.id for r in getattr(member, "roles", [])]
                # NF-15: canali e ruoli senza XP valgono come non idonei.
                id_canale = id_canali_per_le_regole(channel)
                if config.e_escluso(id_canale, id_ruoli):
                    eligible = False
                moltiplicatori[member.id] = config.moltiplicatore(id_canale, id_ruoli)
                presenti.append((member, channel, eligible))

        if not presenti:
            return

        # SEC-10: un utente in blacklist non deve continuare a
        # guadagnare XP vocale.
        bloccati = await blacklist_repo.blacklisted_among([m.id for m, _, _ in presenti])
        presenti = [p for p in presenti if p[0].id not in bloccati]
        if not presenti:
            return

        risultati = await leveling_repo.add_voice_minutes(
            guild.id,
            [(m.id, ch.id, ok) for m, ch, ok in presenti],
            impostazioni=config.impostazioni,
            moltiplicatori=moltiplicatori,
        )
        for member, channel, _ in presenti:
            grant = risultati.get(member.id)
            if grant is None or not grant.leveled_up:
                continue
            # Il canale "corrente" è quello VOCALE stesso: i canali vocali
            # moderni hanno la propria chat integrata, ed è l'unico posto
            # sensato per un task periodico che gira su più server insieme.
            await self._annuncia_level_up(
                member, guild, channel, grant.new_level, config.impostazioni,
                grant.previous_level,
            )
            await self._grant_level_rewards(
                member, guild, grant.new_level, config.impostazioni.reward_mode
            )

    # ================================================================
    # Comandi
    # ================================================================
    @comando_di_gruppo(
        "level",
        nome="rank",
        descrizione="Mostra la rank card: livello, XP, posizione e coin.",
    )
    @app_commands.describe(
        member="Il membro di cui vedere la card (facoltativo)",
        colore="Il tuo colore, es. #FF8800 (resta salvato)",
        tema="Lo sfondo della tua card (resta salvato)",
        reimposta="Torna al colore e al tema di base",
    )
    @app_commands.choices(tema=_SCELTE_TEMA)
    async def rank(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
        colore: app_commands.Range[str, 1, 20] | None = None,
        tema: app_commands.Choice[str] | None = None,
        reimposta: bool | None = None,
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        # NF-12: il disegno e il download dell'avatar possono superare i 3
        # secondi, quindi si risponde subito.
        await interaction.response.defer()

        target = member or interaction.user
        nota = None
        vuole_cambiare = colore is not None or tema is not None or reimposta
        if vuole_cambiare:
            if target.id != interaction.user.id:
                nota = "Puoi cambiare solo la tua card: le preferenze di questo membro non sono cambiate."
            elif reimposta:
                await leveling_repo.reset_rank_card_prefs(target.id)
                nota = "Card riportata al colore e al tema di base."
            else:
                esadecimale = None
                if colore is not None:
                    esadecimale = colore_valido(colore)
                    if esadecimale is None:
                        await interaction.followup.send(
                            "Il colore deve essere nel formato #RRGGBB, per esempio #FF8800.",
                            ephemeral=True,
                        )
                        return
                await leveling_repo.set_rank_card_prefs(
                    target.id, colore=esadecimale, tema=tema.value if tema else None
                )

        totali = await leveling_repo.get_totals(interaction.guild.id, target.id)
        posizione = await leveling_repo.get_xp_position(interaction.guild.id, target.id)
        colore_salvato, tema_salvato = await leveling_repo.get_rank_card_prefs(target.id)

        xp_livello_attuale = xp_for_level(totali.level)
        xp_prossimo_livello = xp_for_level(totali.level + 1)
        progresso = totali.xp_total - xp_livello_attuale
        richiesti = xp_prossimo_livello - xp_livello_attuale
        tetto = (await self._config(interaction.guild.id)).impostazioni.max_level
        if tetto and totali.level >= tetto:
            progresso, richiesti = 0, 0  # al livello massimo non c'è un prossimo livello

        try:
            avatar = await target.display_avatar.read()
        except Exception:  # anche errori di rete (aiohttp) dopo il defer: la card esce senza avatar
            avatar = None
        dati = DatiRankCard(
            nome=target.display_name,
            livello=totali.level,
            xp_nel_livello=progresso,
            xp_richiesti=richiesti,
            xp_totale=totali.xp_total,
            posizione=posizione,
            coin=totali.coins_total,
            colore=colore_salvato or COLORE_DI_BASE,
            tema=tema_salvato or TEMA_DI_BASE,
        )
        try:
            png = await run_image_task(render_rank_card, dati, avatar)
        except Exception:
            logger.exception("Rank card non disegnata per %s: mando l'embed.", target.id)
            embed = discord.Embed(
                title=f"Livello di {target.display_name}", color=discord.Color.blurple()
            )
            embed.set_thumbnail(url=target.display_avatar.url)
            embed.add_field(name="Livello", value=str(totali.level), inline=True)
            embed.add_field(name="XP totale", value=str(totali.xp_total), inline=True)
            embed.add_field(name="Coin", value=str(totali.coins_total), inline=True)
            embed.add_field(
                name="Progresso al prossimo livello",
                value=f"{progresso}/{richiesti} XP" if richiesti else "Livello massimo",
                inline=False,
            )
            await interaction.followup.send(nota, embed=embed)
            return

        await interaction.followup.send(nota, file=discord.File(io.BytesIO(png), filename="rank.png"))

    @comando_di_gruppo(
        "level",
        nome="balance",
        descrizione="Mostra i tuoi coin.",
    )
    @app_commands.describe(member="Il membro di cui vedere il saldo (facoltativo)")
    async def balance(
        self, interaction: discord.Interaction, member: discord.Member | None = None
    ) -> None:
        if await _comando_rifiutato(interaction):
            return

        target = member or interaction.user
        totali = await leveling_repo.get_totals(interaction.guild.id, target.id)
        await interaction.response.send_message(
            f"{target.mention} ha **{totali.coins_total}** coin."
        )

    @comando_di_gruppo(
        "level",
        nome="daily",
        descrizione="Riscuoti la ricompensa giornaliera.",
    )
    async def daily(self, interaction: discord.Interaction) -> None:
        if await _comando_rifiutato(interaction):
            return

        adesso = datetime.now(timezone.utc)
        importo = (await self._config(interaction.guild.id)).impostazioni.daily_coins
        riscosso = await leveling_repo.claim_daily(
            interaction.guild.id, interaction.user.id,
            importo, DAILY_COOLDOWN_SECONDS, adesso,
        )
        if not riscosso:
            totali = await leveling_repo.get_totals(interaction.guild.id, interaction.user.id)
            attesa = seconds_until_next_claim(totali.last_daily_at, DAILY_COOLDOWN_SECONDS)
            await interaction.response.send_message(
                f"Hai già riscosso la ricompensa di oggi. Riprova tra {_format_seconds(attesa)}.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"Hai riscosso **{importo}** coin! Torna domani per altri."
        )

    @comando_di_gruppo(
        "level",
        nome="work",
        descrizione="Lavora per guadagnare qualche coin.",
    )
    async def work(self, interaction: discord.Interaction) -> None:
        if await _comando_rifiutato(interaction):
            return

        adesso = datetime.now(timezone.utc)
        impostazioni = (await self._config(interaction.guild.id)).impostazioni
        guadagno = random.randint(impostazioni.work_min, impostazioni.work_max)
        riscosso = await leveling_repo.claim_work(
            interaction.guild.id, interaction.user.id,
            guadagno, WORK_COOLDOWN_SECONDS, adesso,
        )
        if not riscosso:
            totali = await leveling_repo.get_totals(interaction.guild.id, interaction.user.id)
            attesa = seconds_until_next_claim(totali.last_work_at, WORK_COOLDOWN_SECONDS)
            await interaction.response.send_message(
                f"Sei stanco, riposati un po'. Riprova tra {_format_seconds(attesa)}.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(f"Hai lavorato e guadagnato **{guadagno}** coin!")

    @comando_di_gruppo(
        "level",
        nome="pay",
        descrizione="Trasferisci coin a un altro utente.",
    )
    @app_commands.describe(member="Chi riceve i coin", amount="Quanti coin trasferire")
    async def pay(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        amount: app_commands.Range[int, 1, None],
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        if member.id == interaction.user.id:
            await interaction.response.send_message(
                "Non puoi pagare te stesso.", ephemeral=True
            )
            return
        if member.bot:
            await interaction.response.send_message(
                "Non puoi pagare un bot.", ephemeral=True
            )
            return

        riuscito = await leveling_repo.transfer_coins(
            interaction.guild.id, interaction.user.id, member.id, amount
        )
        if not riuscito:
            await interaction.response.send_message(
                "Non hai abbastanza coin per questo trasferimento.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"{interaction.user.mention} ha trasferito **{amount}** coin a {member.mention}."
        )

    # ================================================================
    # Classifiche
    # ================================================================
    @comando_di_gruppo(
        "level",
        nome="leaderboard",
        descrizione="Mostra la classifica del server.",
    )
    @app_commands.describe(metric="XP o coin", period="Questo mese o di sempre")
    @app_commands.choices(
        metric=[
            app_commands.Choice(name="XP", value="xp"),
            app_commands.Choice(name="Coin", value="coins"),
        ],
        period=[
            app_commands.Choice(name="Questo mese", value="month"),
            app_commands.Choice(name="Di sempre", value="alltime"),
        ],
    )
    async def leaderboard(
        self,
        interaction: discord.Interaction,
        metric: app_commands.Choice[str],
        period: app_commands.Choice[str],
    ) -> None:
        if await _comando_rifiutato(interaction):
            return

        if metric.value == "xp" and period.value == "alltime":
            voci = await leveling_repo.top_xp_alltime(interaction.guild.id)
        elif metric.value == "xp":
            voci = await leveling_repo.top_xp_period(interaction.guild.id)
        elif metric.value == "coins" and period.value == "alltime":
            voci = await leveling_repo.top_coins_alltime(interaction.guild.id)
        else:
            voci = await leveling_repo.top_coins_period(interaction.guild.id)

        if not voci:
            await interaction.response.send_message(
                "Nessun dato ancora disponibile per questa classifica.", ephemeral=True
            )
            return

        righe = []
        for posizione, voce in enumerate(voci, start=1):
            prefisso = MEDALS[posizione - 1] if posizione <= len(MEDALS) else f"{posizione}."
            unita = "XP" if metric.value == "xp" else "coin"
            righe.append(f"{prefisso} <@{voce.user_id}> — **{voce.amount}** {unita}")

        embed = discord.Embed(
            title=f"Classifica {metric.name} — {period.name}",
            description="\n".join(righe),
            color=discord.Color.gold(),
        )
        await interaction.response.send_message(embed=embed)

    # ================================================================
    # Ruoli-premio (SPEC.md §15.13)
    # ================================================================

    @comando_di_gruppo(
        "gestione",
        nome="livello-add",
        descrizione="Assegna un ruolo a chi raggiunge un livello.",
        sottogruppo=_SG_RUOLI,
    )
    @app_commands.describe(
        level="Livello richiesto", role="Ruolo da assegnare al raggiungimento"
    )
    async def level_roles_add(
        self, interaction: discord.Interaction, level: app_commands.Range[int, 1, 1000], role: discord.Role
    ) -> None:
        guild = interaction.guild
        if await _comando_rifiutato(interaction):
            return

        if not isinstance(interaction.user, discord.Member):
            return

        motivo_rifiuto = check_role_assignable(guild, role, interaction.user, self_service=True)
        if motivo_rifiuto is not None:
            await interaction.response.send_message(motivo_rifiuto, ephemeral=True)
            return

        await level_reward_repo.add_reward(guild.id, level_threshold=level, role_id=role.id)
        await interaction.response.send_message(
            f"✅ Chi raggiunge il livello **{level}** riceverà il ruolo {role.mention}.",
            ephemeral=True,
        )

    @comando_di_gruppo(
        "gestione",
        nome="livello-remove",
        descrizione="Rimuove un ruolo-premio configurato.",
        sottogruppo=_SG_RUOLI,
    )
    @app_commands.describe(reward_id="ID della ricompensa (vedi /gestione ruoli livello-list)")
    async def level_roles_remove(self, interaction: discord.Interaction, reward_id: int) -> None:
        guild = interaction.guild
        if await _comando_rifiutato(interaction):
            return

        rimossa = await level_reward_repo.remove_reward(reward_id, guild.id)
        if rimossa:
            await interaction.response.send_message("Ruolo-premio rimosso.", ephemeral=True)
        else:
            await interaction.response.send_message(
                "Nessun ruolo-premio trovato con questo ID in questo server.", ephemeral=True
            )

    @comando_di_gruppo(
        "gestione",
        nome="livello-list",
        descrizione="Mostra i ruoli-premio configurati su questo server.",
        sottogruppo=_SG_RUOLI,
    )
    async def level_roles_list(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if await _comando_rifiutato(interaction):
            return

        ricompense = await level_reward_repo.list_rewards(guild.id)
        if not ricompense:
            await interaction.response.send_message(
                "Nessun ruolo-premio configurato su questo server.", ephemeral=True
            )
            return

        righe = [f"`{r.id}` livello **{r.level_threshold}** → <@&{r.role_id}>" for r in ricompense]
        await invia_lista(
            interaction, "🏅 Ruoli-premio configurati", righe, discord.Color.gold(),
            ephemeral=True, per_pagina=RUOLI_PREMIO_PER_PAGINA,
        )


    # ================================================================
    # Annuncio vincitori mensile (SPEC.md §15.11)
    # ================================================================

    @comando_di_gruppo(
        "gestione",
        nome="vincitori-set",
        descrizione="Imposta il canale dove annunciare i vincitori del mese.",
        sottogruppo=_SG_ECONOMIA,
    )
    @app_commands.describe(channel="Canale dell'annuncio")
    async def monthly_winners_set(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        guild = interaction.guild
        if await _comando_rifiutato(interaction):
            return

        await monthly_winners_repo.set_channel(
            guild.id, channel.id, already_covered_period=previous_period_key()
        )
        await interaction.response.send_message(
            f"✅ I vincitori del mese verranno annunciati in {channel.mention} "
            f"all'inizio di ogni mese (il primo annuncio al prossimo cambio mese).",
            ephemeral=True,
        )

    @comando_di_gruppo(
        "gestione",
        nome="vincitori-off",
        descrizione="Disattiva l'annuncio dei vincitori del mese.",
        sottogruppo=_SG_ECONOMIA,
    )
    async def monthly_winners_disable(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if await _comando_rifiutato(interaction):
            return

        if await monthly_winners_repo.disable(guild.id):
            await interaction.response.send_message("Annuncio mensile disattivato.", ephemeral=True)
        else:
            await interaction.response.send_message(
                "L'annuncio mensile non era attivo su questo server.", ephemeral=True
            )

    # ================================================================
    # Shop (SPEC.md §15.4)
    # ================================================================

    @comando_di_gruppo(
        "level",
        nome="list",
        descrizione="Mostra gli oggetti disponibili nello shop.",
        sottogruppo=_SG_SHOP,
    )
    async def shop_list(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if await _comando_rifiutato(interaction):
            return

        oggetti = await shop_repo.list_items(guild.id)
        if not oggetti:
            await interaction.response.send_message(
                "Lo shop di questo server è vuoto.", ephemeral=True
            )
            return

        righe = []
        for oggetto in oggetti:
            nome = taglia(oggetto.name, MAX_NOME_OGGETTO)
            riga = f"`{oggetto.id}` **{nome}** — {oggetto.price} coin"
            if oggetto.role_id is not None:
                riga += f" (ruolo <@&{oggetto.role_id}>)"
            if oggetto.description:
                riga += f"\n> {taglia(oggetto.description, MAX_DESCRIZIONE_OGGETTO)}"
            righe.append(taglia(riga, LIMITE_RIGA_NEGOZIO))

        await invia_lista(interaction, "🛒 Shop", righe, discord.Color.green())

    @comando_di_gruppo(
        "level",
        nome="buy",
        descrizione="Acquista un oggetto dello shop.",
        sottogruppo=_SG_SHOP,
    )
    @app_commands.describe(item_id="ID dell'oggetto (vedi /level shop list)")
    async def shop_buy(self, interaction: discord.Interaction, item_id: int) -> None:
        guild = interaction.guild
        if await _comando_rifiutato(interaction):
            return
        if guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        oggetto = await shop_repo.get_item(item_id, guild.id)
        if oggetto is None:
            await interaction.response.send_message(
                "Nessun oggetto trovato con questo ID.", ephemeral=True
            )
            return

        # SEC-4/SEC-17: il ruolo si ricontrolla PRIMA di far spendere i
        # coin: può essere stato cancellato o aver preso permessi
        # pericolosi dopo che è stato messo nello shop.
        ruolo_shop = None
        if oggetto.role_id is not None:
            ruolo_shop = guild.get_role(oggetto.role_id)
            if ruolo_shop is None:
                await interaction.response.send_message(
                    "Questo oggetto non è più acquistabile: il suo ruolo non esiste più.",
                    ephemeral=True,
                )
                return
            motivo_rifiuto = check_role_assignable(guild, ruolo_shop, guild.me, self_service=True)
            if motivo_rifiuto is not None:
                await interaction.response.send_message(
                    f"Questo oggetto non è più acquistabile: {motivo_rifiuto}",
                    ephemeral=True,
                )
                return

        acquisto = await shop_repo.buy_item(guild.id, interaction.user.id, oggetto)
        if acquisto.esito == EsitoAcquisto.GIA_ACQUISTATO:
            await interaction.response.send_message(
                "Hai già acquistato questo oggetto.", ephemeral=True
            )
            return
        if acquisto.esito == EsitoAcquisto.SALDO_INSUFFICIENTE:
            await interaction.response.send_message(
                f"Non hai abbastanza coin — servono **{oggetto.price}**.", ephemeral=True
            )
            return

        nome = taglia(oggetto.name, 200)
        conferma = f"✅ Hai acquistato **{nome}** per {oggetto.price} coin!"
        if ruolo_shop is None:
            await interaction.response.send_message(conferma)
            return

        # Da qui si parla con Discord: prima il defer, poi il ruolo.
        await interaction.response.defer()
        try:
            await interaction.user.add_roles(
                ruolo_shop, reason=taglia(f"Acquisto shop: {oggetto.name}", LIMITE_MOTIVO)
            )
        except discord.HTTPException:
            # Il ruolo non è arrivato: l'acquisto si annulla e i coin
            # tornano indietro.
            await shop_repo.refund_purchase(
                acquisto.purchase_id, guild.id, interaction.user.id, oggetto.price
            )
            logger.warning(
                "Impossibile assegnare il ruolo shop %s a %s: acquisto rimborsato.",
                oggetto.role_id,
                interaction.user.id,
            )
            await interaction.followup.send(
                "Non sono riuscito a darti il ruolo: l'acquisto è annullato e i "
                f"**{oggetto.price}** coin ti sono stati restituiti.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(conferma)

    @comando_di_gruppo(
        "gestione",
        nome="shop-add",
        descrizione="Aggiunge un oggetto allo shop.",
        sottogruppo=_SG_ECONOMIA,
    )
    @app_commands.describe(
        name="Nome dell'oggetto",
        price="Prezzo in coin",
        role="Ruolo da assegnare all'acquisto (facoltativo)",
        description="Descrizione (facoltativa)",
    )
    async def shop_add_item(
        self,
        interaction: discord.Interaction,
        name: app_commands.Range[str, 1, MAX_NOME_OGGETTO],
        price: app_commands.Range[int, 1, 1000000],
        role: discord.Role | None = None,
        description: app_commands.Range[str, 1, MAX_DESCRIZIONE_OGGETTO] | None = None,
    ) -> None:
        guild = interaction.guild
        if await _comando_rifiutato(interaction):
            return

        if role is not None and isinstance(interaction.user, discord.Member):
            motivo_rifiuto = check_role_assignable(guild, role, interaction.user, self_service=True)
            if motivo_rifiuto is not None:
                await interaction.response.send_message(motivo_rifiuto, ephemeral=True)
                return

        item_id = await shop_repo.add_item(
            guild.id, name=name, price=price,
            role_id=role.id if role else None, description=description,
        )
        await interaction.response.send_message(
            f"✅ Aggiunto **{name}** allo shop (ID `{item_id}`).", ephemeral=True
        )

    @comando_di_gruppo(
        "gestione",
        nome="shop-remove",
        descrizione="Rimuove un oggetto dallo shop.",
        sottogruppo=_SG_ECONOMIA,
    )
    @app_commands.describe(item_id="ID dell'oggetto (vedi /level shop list)")
    async def shop_remove_item(self, interaction: discord.Interaction, item_id: int) -> None:
        guild = interaction.guild
        if await _comando_rifiutato(interaction):
            return

        if await shop_repo.remove_item(item_id, guild.id):
            await interaction.response.send_message("Oggetto rimosso dallo shop.", ephemeral=True)
        else:
            await interaction.response.send_message(
                "Nessun oggetto trovato con questo ID in questo server.", ephemeral=True
            )

    # ================================================================
    # Cassa di server (SPEC.md §15.15) — alimentata dal decadimento
    # settimanale sui coin personali e da quello mensile della
    # tesoreria di clan, usabile per premi evento e per lo sblocco
    # del bot premium (doppio cancello: tempo dal join del bot +
    # costo in coin, variabile per fascia membri).
    # ================================================================


    @comando_di_gruppo(
        "level",
        nome="cassa",
        descrizione="Mostra il saldo della cassa del server.",
    )
    async def chest_saldo(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if await _comando_rifiutato(interaction):
            return

        saldo = await guild_chest_repo.get_balance(guild.id)
        movimenti = await guild_chest_repo.list_ledger(guild.id, limit=5)

        embed = discord.Embed(
            title="🏛️ Cassa del server",
            description=f"Saldo attuale: **{saldo}** coin",
            color=discord.Color.gold(),
        )
        if movimenti:
            righe = []
            for m in movimenti:
                segno = "+" if m.amount > 0 else ""
                righe.append(f"`{m.created_at:%Y-%m-%d}` {segno}{m.amount} — {m.reason}")
            embed.add_field(name="Ultimi movimenti", value="\n".join(righe), inline=False)
        await interaction.response.send_message(embed=embed)

    @comando_di_gruppo(
        "gestione",
        nome="cassa-premium",
        descrizione="Sblocca un mese di bot premium spendendo dalla cassa.",
        sottogruppo=_SG_ECONOMIA,
    )
    @app_commands.describe(
        tier="Quale mese sbloccare: 1° (dopo 6 mesi), 2° (dopo 1 anno) o 3° (dopo 2 anni)"
    )
    async def chest_sblocca_premium(
        self, interaction: discord.Interaction, tier: app_commands.Range[int, 1, 3]
    ) -> None:
        guild = interaction.guild
        if await _comando_rifiutato(interaction):
            return

        risultato = await purchase_premium_tier(
            guild.id, tier=tier, member_count=guild.member_count or 0
        )

        if risultato.outcome == PurchaseOutcome.GUILD_NOT_CONFIGURED:
            await interaction.response.send_message(
                "Configurazione del server non trovata — riprova più tardi.", ephemeral=True
            )
        elif risultato.outcome == PurchaseOutcome.ALREADY_PURCHASED:
            await interaction.response.send_message(
                f"Il {tier}° mese di premium è già stato acquistato da questo server.",
                ephemeral=True,
            )
        elif risultato.outcome == PurchaseOutcome.TIME_NOT_UNLOCKED:
            mesi_richiesti = TIER_MONTHS_REQUIRED[tier]
            await interaction.response.send_message(
                f"Il {tier}° mese di premium si sblocca solo dopo {mesi_richiesti} mesi "
                "dall'ingresso del bot in questo server — non è ancora passato abbastanza tempo.",
                ephemeral=True,
            )
        elif risultato.outcome == PurchaseOutcome.INSUFFICIENT_FUNDS:
            await interaction.response.send_message(
                f"La cassa non basta — servono **{risultato.cost}** coin per il {tier}° mese.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"✅ {tier}° mese di premium sbloccato per **{risultato.cost}** coin dalla "
                f"cassa! Premium attivo fino al {risultato.new_premium_until:%Y-%m-%d}."
            )

    @comando_di_gruppo(
        "gestione",
        nome="assegna-lobby",
        descrizione="Premio partecipazione: assegna coin a chi è in vocale ORA, dalla cassa del server.",
        sottogruppo=_SG_ECONOMIA,
    )
    @app_commands.describe(importo="Quante coin assegnare a CIASCUNO dei presenti in vocale")
    async def assegna_lobby(
        self, interaction: discord.Interaction, importo: app_commands.Range[int, 1, 1_000_000]
    ) -> None:
        guild = interaction.guild
        if await _comando_rifiutato(interaction):
            return

        # LIM-25: con molte persone il lavoro supera i 3 secondi.
        await interaction.response.defer()

        # I presenti si leggono una volta sola, tutti insieme. SEC-21:
        # chi è in blacklist non riceve il premio e non viene contato
        # nel costo per la cassa.
        in_vocale = {
            membro.id
            for canale in guild.voice_channels
            for membro in canale.members
            if not membro.bot
        }
        presenti = [
            membro_id
            for membro_id in sorted(in_vocale)
            if not await blacklist_repo.is_user_blacklisted(membro_id)
        ]
        if not presenti:
            await interaction.followup.send(
                "Nessuno è in vocale in questo momento — nessuna coin assegnata.", ephemeral=True
            )
            return

        # LC-1: addebito e accrediti in una sola transazione.
        costo_totale = importo * len(presenti)
        riuscito = await guild_chest_repo.pay_members(
            guild.id, presenti, importo, reason=REASON_EVENT_LOBBY_PRIZE
        )
        if not riuscito:
            saldo = await guild_chest_repo.get_balance(guild.id)
            await interaction.followup.send(
                f"La cassa non basta — servono **{costo_totale}** coin per **{len(presenti)}** "
                f"persone in vocale (ne avete **{saldo}**).",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"✅ Assegnate **{importo}** coin a **{len(presenti)}** persone in vocale "
            f"(**{costo_totale}** coin totali dalla cassa)."
        )

    @comando_di_gruppo(
        "gestione",
        nome="assegna-winner",
        descrizione="Premio vincitore: assegna coin a un membro, dalla cassa del server.",
        sottogruppo=_SG_ECONOMIA,
    )
    @app_commands.describe(membro="Il membro da premiare", importo="Quante coin assegnare")
    async def assegna_winner(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        importo: app_commands.Range[int, 1, 1_000_000],
    ) -> None:
        guild = interaction.guild
        if await _comando_rifiutato(interaction):
            return

        # SEC-21: nessun premio a chi è in blacklist.
        if await blacklist_repo.is_user_blacklisted(membro.id):
            await interaction.response.send_message(
                "Questo utente non può ricevere premi.", ephemeral=True
            )
            return

        # Addebito e accredito nella stessa transazione, come /gestione economia assegna-lobby.
        riuscito = await guild_chest_repo.pay_members(
            guild.id, [membro.id], importo, reason=REASON_EVENT_WINNER_PRIZE
        )
        if not riuscito:
            saldo = await guild_chest_repo.get_balance(guild.id)
            await interaction.response.send_message(
                f"La cassa non basta — servono **{importo}** coin (ne avete **{saldo}**).",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"🏆 {membro.mention} ha vinto **{importo}** coin dalla cassa del server!"
        )

    @comando_di_gruppo(
        "gestione",
        nome="xp",
        descrizione="Modifica XP e livello di un membro: aggiungi, togli, imposta, azzera.",
        sottogruppo=_SG_ECONOMIA,
    )
    @app_commands.describe(
        azione="Cosa fare",
        membro="Il membro",
        valore="XP o livello (non serve per azzerare)",
    )
    @app_commands.choices(azione=_SCELTE_AZIONE_XP)
    async def gestione_xp(
        self,
        interaction: discord.Interaction,
        azione: app_commands.Choice[str],
        membro: discord.Member,
        valore: app_commands.Range[int, 0, 10_000_000] = 0,
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        if membro.bot:
            await interaction.response.send_message(
                "I bot non hanno XP.", ephemeral=True
            )
            return
        if azione.value != "azzera" and valore == 0 and azione.value in ("aggiungi", "togli"):
            await interaction.response.send_message(
                "Indica quanti XP (almeno 1).", ephemeral=True
            )
            return
        # Dopo la scrittura si toccano i ruoli su Discord: si risponde con defer.
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        config = await self._config(guild.id)
        tetto = config.impostazioni.max_level
        esito = await leveling_repo.modifica_xp(
            guild.id, membro.id, azione.value, valore, tetto
        )
        await self._grant_level_rewards(
            membro, guild, esito.livello_dopo, config.impostazioni.reward_mode,
            togli_superiori=True,
        )
        logger.info(
            "XP modificati dallo staff: server %s, staff %s, membro %s, %s %s (%s -> %s).",
            guild.id, interaction.user.id, membro.id, azione.value, valore,
            esito.xp_prima, esito.xp_dopo,
        )
        await interaction.followup.send(
            f"✅ {membro.mention}: livello **{esito.livello_prima} → {esito.livello_dopo}**, "
            f"XP **{esito.xp_prima} → {esito.xp_dopo}**.",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @comando_di_gruppo(
        "gestione",
        nome="monete",
        descrizione="Modifica il saldo di un membro: aggiungi, togli, imposta, azzera.",
        sottogruppo=_SG_ECONOMIA,
    )
    @app_commands.describe(
        azione="Cosa fare", membro="Il membro", importo="Quante coin (non serve per azzerare)"
    )
    @app_commands.choices(azione=_SCELTE_AZIONE_MONETE)
    async def gestione_monete(
        self,
        interaction: discord.Interaction,
        azione: app_commands.Choice[str],
        membro: discord.Member,
        importo: app_commands.Range[int, 0, 1_000_000_000] | None = None,
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        if membro.bot:
            await interaction.response.send_message("I bot non hanno coin.", ephemeral=True)
            return
        if azione.value != "azzera" and not importo and not (azione.value == "imposta" and importo == 0):
            await interaction.response.send_message(
                "Indica l'importo.", ephemeral=True
            )
            return
        guild = interaction.guild
        esito = await leveling_repo.modifica_monete(
            guild.id, membro.id, azione.value, importo or 0
        )
        logger.info(
            "Coin modificate dallo staff: server %s, staff %s, membro %s, %s %s (%s -> %s).",
            guild.id, interaction.user.id, membro.id, azione.value, importo,
            esito.prima, esito.dopo,
        )
        await interaction.response.send_message(
            f"✅ {membro.mention}: saldo **{esito.prima} → {esito.dopo}** coin.",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    # ================================================================
    # Sistema Gilde/Clan (SPEC.md §15.14) — primo pezzo di comandi:
    # crea, info, membri, classifica, tesoreria/dona, sciogli. Il
    # motore economico (tick vocale, decadimento, XP) è già completo
    # a livello di repository/worker da prima — qui arrivano i primi
    # comandi Discord per usarlo davvero. Inviti/espulsioni/
    # promozioni, acquisto canali e boost restano il pezzo successivo.
    # ================================================================


    @comando_di_gruppo(
        "clan",
        nome="crea",
        descrizione="Crea una nuova gilda/clan.",
    )
    @app_commands.describe(
        tag=f"Tag della gilda (1-5 caratteri, niente emoji né spazi)",
        name="Nome completo della gilda",
    )
    async def clan_crea(
        self,
        interaction: discord.Interaction,
        tag: app_commands.Range[str, TAG_MIN_LENGTH, TAG_MAX_LENGTH],
        name: app_commands.Range[str, 1, MAX_NOME_CLAN],
    ) -> None:
        guild = interaction.guild
        if await _comando_rifiutato(interaction):
            return
        if guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        # LIM-25: più chiamate a Discord, quindi defer() per primo.
        await interaction.response.defer()

        valido, motivo = validate_guild_tag(tag)
        if not valido:
            await interaction.followup.send(motivo, ephemeral=True)
            return

        if await guild_clan_repo.get_member_clan_in_guild(guild.id, interaction.user.id):
            await interaction.followup.send(
                "Fai già parte di una gilda in questo server — lasciala prima di crearne una nuova.",
                ephemeral=True,
            )
            return

        if await guild_clan_repo.is_tag_taken(guild.id, tag):
            await interaction.followup.send(
                f"Il tag `{tag}` è già usato da un'altra gilda in questo server.",
                ephemeral=True,
            )
            return

        try:
            categoria = await guild.create_category(
                name=f"[{tag}] {name}"[:100],
                overwrites={
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    interaction.user: discord.PermissionOverwrite(
                        view_channel=True, send_messages=True, manage_channels=True
                    ),
                    guild.me: discord.PermissionOverwrite(
                        view_channel=True, send_messages=True, manage_channels=True
                    ),
                },
                reason=taglia(f"Creazione gilda '{tag}' da {interaction.user}", LIMITE_MOTIVO),
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "Non ho i permessi per creare una categoria in questo server.", ephemeral=True
            )
            return
        except discord.HTTPException:
            await interaction.followup.send(
                "Creazione della categoria fallita — riprova più tardi.", ephemeral=True
            )
            return

        scadenza = datetime.now(timezone.utc) + timedelta(hours=CREATION_GRACE_HOURS)
        clan_id = await guild_clan_repo.create_clan(
            guild.id, tag=tag, name=name, owner_id=interaction.user.id,
            officialize_deadline=scadenza,
        )
        if clan_id is None:
            # Un'altra richiesta è arrivata un attimo prima (stesso tag,
            # oppure il fondatore è appena entrato in un'altra gilda):
            # la categoria appena creata non serve più.
            try:
                await categoria.delete(reason=f"Gilda '{tag}' non creata")
            except discord.HTTPException:
                logger.warning("Impossibile eliminare la categoria %s rimasta senza gilda.", categoria.id)
            if await guild_clan_repo.is_tag_taken(guild.id, tag):
                motivo = f"Il tag `{tag}` è già usato da un'altra gilda in questo server."
            else:
                motivo = "Fai già parte di una gilda in questo server."
            await interaction.followup.send(motivo, ephemeral=True)
            return
        await guild_clan_repo.set_category_id(clan_id, categoria.id)
        await sync_member_clan_role(guild, categoria, interaction.user, ROLE_OWNER)

        await interaction.followup.send(
            f"✅ Gilda **{name}** (`{tag}`) creata! Per ufficializzarla servono "
            f"**{CREATION_DEFICIT}** coin in tesoreria entro **{CREATION_GRACE_HOURS} ore** "
            f"(`/clan tesoreria dona`) — altrimenti verrà eliminata automaticamente."
        )

    @comando_di_gruppo(
        "clan",
        nome="info",
        descrizione="Mostra le informazioni di una gilda.",
    )
    @app_commands.describe(tag="Tag della gilda (facoltativo: la tua, se non specificato)")
    async def clan_info(
        self,
        interaction: discord.Interaction,
        tag: app_commands.Range[str, TAG_MIN_LENGTH, TAG_MAX_LENGTH] | None = None,
    ) -> None:
        guild = interaction.guild
        if await _comando_rifiutato(interaction):
            return

        if tag is not None:
            clan = await guild_clan_repo.get_clan_by_tag(guild.id, tag)
        else:
            clan = await guild_clan_repo.get_member_clan_in_guild(guild.id, interaction.user.id)

        if clan is None:
            await interaction.response.send_message(
                "Nessuna gilda trovata." if tag else "Non fai parte di nessuna gilda in questo server.",
                ephemeral=True,
            )
            return

        n_membri = await guild_clan_repo.count_members(clan.id)
        stato = "✅ Ufficializzata" if clan.officialized else (
            f"⏳ In attesa (scade <t:{int(clan.officialize_deadline.timestamp())}:R>)"
        )

        embed = discord.Embed(
            title=taglia(f"🛡️ [{clan.tag}] {clan.name}", LIMITE_TITOLO_EMBED),
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Stato", value=stato, inline=False)
        embed.add_field(name="Capo Clan", value=f"<@{clan.owner_id}>", inline=True)
        if clan.co_owner_id is not None:
            embed.add_field(name="Co-Owner", value=f"<@{clan.co_owner_id}>", inline=True)
        embed.add_field(name="Membri", value=f"{n_membri}/{clan.max_members}", inline=True)
        embed.add_field(name="Tesoreria", value=f"{clan.treasury_balance} coin", inline=True)
        embed.add_field(name="XP totale", value=str(clan.total_xp), inline=True)
        ore_accumulate = voice_ticks_to_hours(clan.total_voice_ticks)
        ore_richieste = next_channel_voice_hours_requirement(clan.channels_unlocked)
        prossimo_costo = next_channel_unlock_cost(clan.channels_unlocked)
        if prossimo_costo is None:
            valore_canali = f"{clan.channels_unlocked} (massimo raggiunto)"
        else:
            valore_canali = (
                f"{clan.channels_unlocked} — prossimo: **{prossimo_costo}** coin + "
                f"**{ore_richieste}**h vocali (ne avete {ore_accumulate})"
            )
        embed.add_field(name="Canali sbloccati", value=valore_canali, inline=False)

        righe_boost = _righe_boost_attivi(
            benefici_attivi(
                clan.guild_boost_exp_expires_at,
                clan.guild_boost_coin_expires_at,
                datetime.now(timezone.utc),
            )
        )
        if righe_boost:
            embed.add_field(name="Boost di gilda", value="\n".join(righe_boost), inline=False)

        movimenti = await guild_clan_repo.list_ledger(clan.id, limit=MOVIMENTI_IN_CLAN_INFO)
        if movimenti:
            embed.add_field(
                name="Ultimi movimenti",
                value="\n".join(_riga_movimento(m) for m in movimenti),
                inline=False,
            )

        await interaction.response.send_message(embed=embed)

    @comando_di_gruppo(
        "clan",
        nome="membri",
        descrizione="Mostra i membri di una gilda.",
    )
    @app_commands.describe(tag="Tag della gilda (facoltativo: la tua, se non specificato)")
    async def clan_membri(
        self,
        interaction: discord.Interaction,
        tag: app_commands.Range[str, TAG_MIN_LENGTH, TAG_MAX_LENGTH] | None = None,
    ) -> None:
        guild = interaction.guild
        if await _comando_rifiutato(interaction):
            return

        if tag is not None:
            clan = await guild_clan_repo.get_clan_by_tag(guild.id, tag)
        else:
            clan = await guild_clan_repo.get_member_clan_in_guild(guild.id, interaction.user.id)

        if clan is None:
            await interaction.response.send_message(
                "Nessuna gilda trovata." if tag else "Non fai parte di nessuna gilda in questo server.",
                ephemeral=True,
            )
            return

        membri = await guild_clan_repo.list_members(clan.id)
        righe = [f"<@{m.user_id}> — {m.role}" for m in membri] or ["Nessun membro."]
        await invia_lista(
            interaction, f"Membri di [{clan.tag}] {clan.name}", righe,
            discord.Color.blurple(), per_pagina=MEMBRI_PER_PAGINA,
        )

    @comando_di_gruppo(
        "clan",
        nome="classifica",
        descrizione="Classifica delle gilde per XP (mensile o totale).",
    )
    @app_commands.describe(period="Questo mese o di sempre")
    @app_commands.choices(
        period=[
            app_commands.Choice(name="Questo mese", value="month"),
            app_commands.Choice(name="Di sempre", value="alltime"),
        ]
    )
    async def clan_classifica(
        self,
        interaction: discord.Interaction,
        period: app_commands.Choice[str] | None = None,
    ) -> None:
        guild = interaction.guild
        if await _comando_rifiutato(interaction):
            return

        # Default: totale all-time (comportamento storico del
        # comando, invariato per chi lo usa senza specificare nulla).
        mensile = period is not None and period.value == "month"

        if mensile:
            voci = await guild_clan_repo.get_monthly_clan_leaderboard(guild.id)
            if not voci:
                await interaction.response.send_message(
                    "Nessuna gilda ha guadagnato XP questo mese in questo server.",
                    ephemeral=True,
                )
                return
            righe = [
                f"**{i+1}.** [{c.tag}] {taglia(c.name, MAX_NOME_CLAN)} — {xp} XP"
                for i, (c, xp) in enumerate(voci)
            ]
            titolo = "🏆 Classifica Gilde — questo mese"
        else:
            classifica = await guild_clan_repo.get_clan_leaderboard(guild.id)
            if not classifica:
                await interaction.response.send_message(
                    "Nessuna gilda in questo server ancora.", ephemeral=True
                )
                return
            righe = [
                f"**{i+1}.** [{c.tag}] {taglia(c.name, MAX_NOME_CLAN)} — {c.total_xp} XP"
                for i, c in enumerate(classifica)
            ]
            titolo = "🏆 Classifica Gilde — di sempre"

        embed = discord.Embed(
            title=titolo, description="\n".join(righe), color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed)


    @comando_di_gruppo(
        "clan",
        nome="set",
        descrizione="Imposta il canale dove annunciare la top 3 gilde del mese.",
        sottogruppo=_SG_BACHECA,
    )
    @app_commands.describe(channel="Canale dell'annuncio (la 'bacheca clan')")
    @richiedi(Livello.ADMIN)
    async def clan_bacheca_set(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        guild = interaction.guild
        if await _comando_rifiutato(interaction):
            return

        await clan_leaderboard_config_repo.set_channel(
            guild.id, channel.id, already_covered_period=clan_previous_period_key()
        )
        await interaction.response.send_message(
            f"✅ La top 3 gilde del mese verrà annunciata in {channel.mention} "
            f"all'inizio di ogni mese (il primo annuncio al prossimo cambio mese).",
            ephemeral=True,
        )

    @comando_di_gruppo(
        "clan",
        nome="disable",
        descrizione="Disattiva l'annuncio automatico della top 3 gilde.",
        sottogruppo=_SG_BACHECA,
    )
    @richiedi(Livello.ADMIN)
    async def clan_bacheca_disable(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if await _comando_rifiutato(interaction):
            return

        if await clan_leaderboard_config_repo.disable(guild.id):
            await interaction.response.send_message(
                "Annuncio della top 3 gilde disattivato.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "L'annuncio della top 3 gilde non era attivo su questo server.", ephemeral=True
            )

    @comando_di_gruppo(
        "clan",
        nome="sciogli",
        descrizione="Sciogli la tua gilda.",
    )
    async def clan_sciogli(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if await _comando_rifiutato(interaction):
            return

        # LIM-25: più chiamate a Discord, quindi defer() per primo.
        await interaction.response.defer()

        clan = await guild_clan_repo.get_member_clan_in_guild(guild.id, interaction.user.id)
        if clan is None:
            await interaction.followup.send(
                "Non fai parte di nessuna gilda in questo server.", ephemeral=True
            )
            return
        if clan.owner_id != interaction.user.id:
            await interaction.followup.send(
                "Solo il Capo Clan può sciogliere la gilda.", ephemeral=True
            )
            return

        categoria = None
        if clan.category_id is not None:
            categoria = guild.get_channel(clan.category_id)

        # Il Capo Clan è chi chiama il comando: si pulisce con l'oggetto
        # Member già in mano. Gli altri ufficiali (co-owner, Admin Clan)
        # perdono anche loro il ruolo condiviso; gli overwrite spariscono
        # con la categoria.
        await clear_member_clan_presence(guild, categoria, interaction.user)
        altri = [
            socio for socio in await guild_clan_repo.list_members(clan.id)
            if socio.user_id != interaction.user.id
        ]
        await clear_clan_officers_presence(guild, None, altri)

        if categoria is not None:
            for canale in list(categoria.channels):
                try:
                    await canale.delete(reason=f"Gilda '{clan.tag}' sciolta")
                except discord.HTTPException:
                    logger.warning("Impossibile eliminare il canale %s della gilda %s.", canale.id, clan.id)
            try:
                await categoria.delete(reason=f"Gilda '{clan.tag}' sciolta")
            except discord.HTTPException:
                logger.warning("Impossibile eliminare la categoria della gilda %s.", clan.id)

        await guild_clan_repo.delete_clan(clan.id)
        await interaction.followup.send(f"La gilda **{clan.name}** è stata sciolta.")

    @comando_di_gruppo(
        "clan",
        nome="invita",
        descrizione="Invita un membro nella tua gilda.",
    )
    @app_commands.describe(membro="Il membro da invitare nella tua gilda")
    async def clan_invita(self, interaction: discord.Interaction, membro: discord.Member) -> None:
        guild = interaction.guild
        if await _comando_rifiutato(interaction):
            return

        # LIM-25: più chiamate a Discord, quindi defer() per primo.
        await interaction.response.defer()

        clan = await guild_clan_repo.get_member_clan_in_guild(guild.id, interaction.user.id)
        if clan is None:
            await interaction.followup.send(
                "Non fai parte di nessuna gilda in questo server.", ephemeral=True
            )
            return

        chi_invita = await guild_clan_repo.get_member(clan.id, interaction.user.id)
        if chi_invita is None or chi_invita.role not in RUOLI_UFFICIALI:
            await interaction.followup.send(
                "Solo il Capo Clan, il Co-Owner o un Admin Clan possono invitare nuovi membri.", ephemeral=True
            )
            return

        if membro.bot:
            await interaction.followup.send(
                "Non puoi invitare un bot in una gilda.", ephemeral=True
            )
            return

        if await guild_clan_repo.get_member_clan_in_guild(guild.id, membro.id) is not None:
            await interaction.followup.send(
                f"{membro.mention} fa già parte di una gilda in questo server.", ephemeral=True
            )
            return

        if await guild_clan_repo.count_members(clan.id) >= clan.max_members:
            await interaction.followup.send(
                f"La gilda ha già raggiunto il limite di **{clan.max_members}** membri.", ephemeral=True
            )
            return

        # M 9.8: l'invitato entra solo se accetta. I controlli qui sopra
        # servono a dare subito un messaggio chiaro; quelli che contano
        # si rifanno dentro la scrittura quando preme "Accetta".
        scadenza = int(
            (datetime.now(timezone.utc) + timedelta(hours=VALIDITA_INVITO_ORE)).timestamp()
        )
        view = BaseView(timeout=None)
        view.add_item(BottoneInvitoClan("accetta", clan.id, membro.id, scadenza))
        view.add_item(BottoneInvitoClan("rifiuta", clan.id, membro.id, scadenza))
        await interaction.followup.send(
            f"{membro.mention}, {interaction.user.mention} ti invita nella gilda "
            f"**{taglia(clan.name, MAX_NOME_CLAN)}** (`{clan.tag}`). "
            f"L'invito scade <t:{scadenza}:R>.",
            view=view,
        )

    @comando_di_gruppo(
        "clan",
        nome="lascia",
        descrizione="Lascia la gilda di cui fai parte.",
    )
    async def clan_lascia(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if await _comando_rifiutato(interaction):
            return

        # LIM-25: ruoli e permessi sono più chiamate a Discord.
        await interaction.response.defer(ephemeral=True)

        clan = await guild_clan_repo.get_member_clan_in_guild(guild.id, interaction.user.id)
        if clan is None:
            await interaction.followup.send(
                "Non fai parte di nessuna gilda in questo server.", ephemeral=True
            )
            return
        if clan.owner_id == interaction.user.id:
            await interaction.followup.send(
                "Il Capo Clan non può lasciare la gilda — usa `/clan sciogli` per scioglierla.",
                ephemeral=True,
            )
            return

        await guild_clan_repo.remove_member(clan.id, interaction.user.id)

        categoria = guild.get_channel(clan.category_id) if clan.category_id is not None else None
        await clear_member_clan_presence(guild, categoria, interaction.user)

        await interaction.followup.send(
            f"Hai lasciato la gilda **{taglia(clan.name, MAX_NOME_CLAN)}**.", ephemeral=True
        )

    @comando_di_gruppo(
        "clan",
        nome="espelli",
        descrizione="Espelli un membro dalla tua gilda.",
    )
    @app_commands.describe(membro="Il membro da espellere dalla tua gilda")
    async def clan_espelli(self, interaction: discord.Interaction, membro: discord.Member) -> None:
        guild = interaction.guild
        if await _comando_rifiutato(interaction):
            return

        # LIM-25: più chiamate a Discord, quindi defer() per primo.
        await interaction.response.defer()

        clan = await guild_clan_repo.get_member_clan_in_guild(guild.id, interaction.user.id)
        if clan is None:
            await interaction.followup.send(
                "Non fai parte di nessuna gilda in questo server.", ephemeral=True
            )
            return

        chi_espelle = await guild_clan_repo.get_member(clan.id, interaction.user.id)
        if chi_espelle is None or chi_espelle.role not in RUOLI_UFFICIALI:
            await interaction.followup.send(
                "Solo il Capo Clan, il Co-Owner o un Admin Clan possono espellere membri.", ephemeral=True
            )
            return

        target = await guild_clan_repo.get_member(clan.id, membro.id)
        if target is None:
            await interaction.followup.send(
                f"{membro.mention} non fa parte della tua gilda.", ephemeral=True
            )
            return

        if membro.id == clan.owner_id:
            await interaction.followup.send(
                "Il Capo Clan non può essere espulso — usa `/clan sciogli` per sciogliere la gilda.",
                ephemeral=True,
            )
            return

        if chi_espelle.role == ROLE_ADMIN and target.role in (ROLE_ADMIN, ROLE_CO_OWNER):
            await interaction.followup.send(
                "Un Admin Clan non può espellere un altro Admin Clan né il Co-Owner — "
                "serve il Capo Clan.",
                ephemeral=True,
            )
            return

        await guild_clan_repo.remove_member(clan.id, membro.id)

        categoria = guild.get_channel(clan.category_id) if clan.category_id is not None else None
        await clear_member_clan_presence(guild, categoria, membro)

        await interaction.followup.send(
            f"✅ {membro.mention} è stato espulso da **{clan.name}**."
        )

    @comando_di_gruppo(
        "clan",
        nome="promuovi",
        descrizione="Cambia il ruolo di un membro della tua gilda.",
    )
    @app_commands.describe(membro="Il membro a cui cambiare ruolo", ruolo="Il nuovo ruolo da assegnare")
    async def clan_promuovi(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        ruolo: Literal["co_owner", "admin", "mod", "member"],
    ) -> None:
        guild = interaction.guild
        if await _comando_rifiutato(interaction):
            return

        # LIM-25: più chiamate a Discord, quindi defer() per primo.
        await interaction.response.defer()

        clan = await guild_clan_repo.get_member_clan_in_guild(guild.id, interaction.user.id)
        if clan is None:
            await interaction.followup.send(
                "Non fai parte di nessuna gilda in questo server.", ephemeral=True
            )
            return

        if clan.owner_id != interaction.user.id:
            await interaction.followup.send(
                "Solo il Capo Clan può cambiare il ruolo dei membri.", ephemeral=True
            )
            return

        if membro.id == clan.owner_id:
            await interaction.followup.send(
                "Il Capo Clan non può cambiare il proprio ruolo.", ephemeral=True
            )
            return

        target = await guild_clan_repo.get_member(clan.id, membro.id)
        if target is None:
            await interaction.followup.send(
                f"{membro.mention} non fa parte della tua gilda.", ephemeral=True
            )
            return

        tetti = {ROLE_ADMIN: MAX_ADMINS_PER_CLAN, ROLE_MOD: MAX_MODS_PER_CLAN}
        nomi_tetto = {ROLE_ADMIN: "Admin Clan", ROLE_MOD: "Mod Clan"}
        esito = await guild_clan_repo.set_member_role(
            clan.id, membro.id, ruolo, max_with_role=tetti.get(ruolo)
        )
        if esito == EsitoRuolo.TETTO_RAGGIUNTO:
            await interaction.followup.send(
                f"La gilda ha già raggiunto il limite di **{tetti[ruolo]}** {nomi_tetto[ruolo]}.",
                ephemeral=True,
            )
            return
        if esito == EsitoRuolo.NON_MEMBRO:
            await interaction.followup.send(
                f"{membro.mention} non fa parte della tua gilda.", ephemeral=True
            )
            return
        if esito == EsitoRuolo.CO_OWNER_GIA_PRESO:
            await interaction.followup.send(
                "La gilda ha già un Co-Owner: riportalo prima a un altro ruolo.",
                ephemeral=True,
            )
            return

        categoria = guild.get_channel(clan.category_id) if clan.category_id is not None else None
        await sync_member_clan_role(guild, categoria, membro, ruolo)

        await interaction.followup.send(
            f"✅ {membro.mention} è ora **{ruolo}** in **{clan.name}**."
        )

    @comando_di_gruppo(
        "clan",
        nome="compra-canale",
        descrizione="Sblocca un nuovo canale extra per la tua gilda.",
    )
    @app_commands.describe(
        tipo="Tipo di canale da creare",
        nome="Nome del canale (facoltativo: generato dal tag della gilda se non specificato)",
    )
    async def clan_compra_canale(
        self,
        interaction: discord.Interaction,
        tipo: Literal["testuale", "vocale", "forum"],
        nome: app_commands.Range[str, 1, MAX_NOME_CANALE] | None = None,
    ) -> None:
        guild = interaction.guild
        if await _comando_rifiutato(interaction):
            return

        # LIM-25: più chiamate a Discord, quindi defer() per primo.
        await interaction.response.defer()

        clan = await guild_clan_repo.get_member_clan_in_guild(guild.id, interaction.user.id)
        if clan is None:
            await interaction.followup.send(
                "Non fai parte di nessuna gilda in questo server.", ephemeral=True
            )
            return

        chi_acquista = await guild_clan_repo.get_member(clan.id, interaction.user.id)
        if chi_acquista is None or chi_acquista.role not in RUOLI_UFFICIALI:
            await interaction.followup.send(
                "Solo il Capo Clan, il Co-Owner o un Admin Clan possono acquistare nuovi canali.", ephemeral=True
            )
            return

        costo = next_channel_unlock_cost(clan.channels_unlocked)
        if costo is None:
            await interaction.followup.send(
                "La tua gilda ha già sbloccato tutti i canali extra disponibili.", ephemeral=True
            )
            return

        ore_richieste = next_channel_voice_hours_requirement(clan.channels_unlocked)
        ore_accumulate = voice_ticks_to_hours(clan.total_voice_ticks)
        if ore_accumulate < ore_richieste:
            await interaction.followup.send(
                f"Servono **{ore_richieste}** ore vocali accumulate dalla gilda per il prossimo "
                f"canale (ne avete accumulate **{ore_accumulate}**).",
                ephemeral=True,
            )
            return

        if clan.treasury_balance < costo:
            await interaction.followup.send(
                f"La tesoreria della gilda non basta — servono **{costo}** coin "
                f"(ne avete **{clan.treasury_balance}**).",
                ephemeral=True,
            )
            return

        categoria = guild.get_channel(clan.category_id) if clan.category_id is not None else None
        if categoria is None:
            await interaction.followup.send(
                "La categoria della tua gilda non esiste più su Discord — contatta lo staff.",
                ephemeral=True,
            )
            return

        # Prima l'addebito (una sola UPDATE con i controlli dentro),
        # poi il canale su Discord. Se un altro acquisto è arrivato un
        # attimo prima, questo non passa.
        if not await guild_clan_repo.unlock_channel(clan.id, clan.channels_unlocked, costo):
            await interaction.followup.send(
                "L'acquisto non è andato a buon fine: la tesoreria o i canali sbloccati sono "
                "cambiati nel frattempo. Riprova.",
                ephemeral=True,
            )
            return

        nome_canale = (nome or f"{clan.tag.lower()}-canale-{clan.channels_unlocked + 1}")[:100]
        motivo = taglia(f"Canale extra sbloccato per la gilda '{clan.tag}'", LIMITE_MOTIVO)
        try:
            if tipo == "testuale":
                await guild.create_text_channel(nome_canale, category=categoria, reason=motivo)
            elif tipo == "vocale":
                await guild.create_voice_channel(nome_canale, category=categoria, reason=motivo)
            else:
                await guild.create_forum(nome_canale, category=categoria, reason=motivo)
        except discord.HTTPException as errore:
            # Il canale non è nato: la spesa si annulla.
            await guild_clan_repo.refund_channel_unlock(clan.id, costo)
            if isinstance(errore, discord.Forbidden):
                testo = "Non ho i permessi per creare un canale in questa categoria."
            else:
                testo = "Creazione del canale fallita — riprova più tardi."
            await interaction.followup.send(
                f"{testo} I **{costo}** coin sono tornati in tesoreria.", ephemeral=True
            )
            return

        await interaction.followup.send(
            f"✅ Nuovo canale **{tipo}** sbloccato per **{clan.name}** — spesi **{costo}** coin "
            f"dalla tesoreria."
        )


    @comando_di_gruppo(
        "clan",
        nome="dona",
        descrizione="Dona coin personali alla tesoreria della tua gilda.",
        sottogruppo=_SG_TESORERIA,
    )
    @app_commands.describe(importo="Quante coin donare (dal tuo saldo personale)")
    async def clan_tesoreria_dona(
        self, interaction: discord.Interaction, importo: app_commands.Range[int, 1, 1_000_000_000]
    ) -> None:
        guild = interaction.guild
        if await _comando_rifiutato(interaction):
            return

        clan = await guild_clan_repo.get_member_clan_in_guild(guild.id, interaction.user.id)
        if clan is None:
            await interaction.response.send_message(
                "Non fai parte di nessuna gilda in questo server.", ephemeral=True
            )
            return

        nuovo_saldo = await guild_clan_repo.donate_from_member(
            guild.id, clan.id, interaction.user.id, importo
        )
        if nuovo_saldo is None:
            await interaction.response.send_message(
                f"Non hai abbastanza coin personali — servono **{importo}**.", ephemeral=True
            )
            return

        messaggio = f"✅ Hai donato **{importo}** coin alla tesoreria di **{clan.name}** (saldo: {nuovo_saldo})."
        # La gilda diventa ufficiale dentro la donazione stessa (repository).
        if not clan.officialized and is_creation_deficit_covered(nuovo_saldo):
            messaggio += "\n🎉 Il deficit di creazione è coperto: la gilda è ora **ufficializzata**!"

        await interaction.response.send_message(messaggio)

    @comando_di_gruppo(
        "clan",
        nome="trasferisci",
        descrizione="Trasferisci coin dalla tesoreria a un'altra TUA gilda (anche su un altro server).",
        sottogruppo=_SG_TESORERIA,
    )
    @app_commands.describe(
        tag_destinazione="Tag dell'altra gilda di cui sei Capo Clan (anche su un server diverso)",
        importo="Quante coin trasferire dalla tesoreria di questa gilda",
    )
    async def clan_tesoreria_trasferisci(
        self,
        interaction: discord.Interaction,
        tag_destinazione: app_commands.Range[str, TAG_MIN_LENGTH, TAG_MAX_LENGTH],
        importo: app_commands.Range[int, 1, 1_000_000_000],
    ) -> None:
        guild = interaction.guild
        if await _comando_rifiutato(interaction):
            return

        clan = await guild_clan_repo.get_member_clan_in_guild(guild.id, interaction.user.id)
        if clan is None:
            await interaction.response.send_message(
                "Non fai parte di nessuna gilda in questo server.", ephemeral=True
            )
            return

        if clan.owner_id != interaction.user.id:
            await interaction.response.send_message(
                "Solo il Capo Clan può trasferire la tesoreria verso un'altra tua gilda.",
                ephemeral=True,
            )
            return

        # L'UNICA condizione per un trasferimento tra tesorerie è lo
        # stesso owner — MAI lo stesso server: un Capo Clan può avere
        # una seconda gilda su un altro server con lo stesso bot, e
        # senza questo le coin di quella gilda resterebbero bloccate
        # per sempre nel server in cui sono state guadagnate.
        proprie_gilde = await guild_clan_repo.list_clans_owned_by(interaction.user.id)
        candidate = [c for c in proprie_gilde if c.tag == tag_destinazione and c.id != clan.id]

        if not candidate:
            await interaction.response.send_message(
                f"Non sei Capo Clan di nessun'altra gilda con tag `{tag_destinazione}` "
                f"(su nessun server).",
                ephemeral=True,
            )
            return
        if len(candidate) > 1:
            await interaction.response.send_message(
                f"Hai più di una gilda con tag `{tag_destinazione}` (su server diversi) — "
                f"rinomina il tag di una delle due per distinguerle prima di trasferire.",
                ephemeral=True,
            )
            return

        destinazione = candidate[0]
        riuscito = await guild_clan_repo.transfer_between_treasuries(clan.id, destinazione.id, importo)
        if not riuscito:
            await interaction.response.send_message(
                f"La tesoreria di **{clan.name}** non basta — servono **{importo}** coin "
                f"(ne avete **{clan.treasury_balance}**).",
                ephemeral=True,
            )
            return

        nota_cross_server = (
            " (su un altro server)" if destinazione.guild_id != guild.id else ""
        )
        messaggio = (
            f"✅ Trasferite **{importo}** coin dalla tesoreria di **{clan.name}** a "
            f"**{destinazione.name}**{nota_cross_server}."
        )
        # BUG-15: il trasferimento può aver coperto il debito di creazione.
        aggiornata = await guild_clan_repo.get_clan_by_tag(
            destinazione.guild_id, destinazione.tag
        )
        if aggiornata is not None and aggiornata.officialized and not destinazione.officialized:
            messaggio += (
                f"\n🎉 Il deficit di creazione è coperto: **{destinazione.name}** è ora "
                "**ufficializzata**!"
            )
        await interaction.response.send_message(messaggio)


    @comando_di_gruppo(
        "clan",
        nome="individuale",
        descrizione=f"Acquista un boost personale ×{BOOST_MULTIPLIER} per {BOOST_DURATION_HOURS}h sul tuo tick vocale di gilda.",
        sottogruppo=_SG_BOOST,
    )
    @app_commands.describe(tipo="Cosa raddoppia: exp, coin o entrambi (super)")
    @app_commands.choices(tipo=_scelte_boost(INDIVIDUAL_BOOST_COSTS))
    async def clan_boost_individuale(
        self, interaction: discord.Interaction, tipo: app_commands.Choice[str]
    ) -> None:
        guild = interaction.guild
        if await _comando_rifiutato(interaction):
            return

        clan = await guild_clan_repo.get_member_clan_in_guild(guild.id, interaction.user.id)
        if clan is None:
            await interaction.response.send_message(
                "Non fai parte di nessuna gilda in questo server.", ephemeral=True
            )
            return

        tipo_boost = _tipo_da_scelta(tipo)
        costo = INDIVIDUAL_BOOST_COSTS[tipo_boost]
        adesso = datetime.now(timezone.utc)
        esito = await guild_clan_repo.buy_member_boost(
            guild.id, clan.id, interaction.user.id, tipo_boost, adesso
        )
        if esito.stato is StatoBoost.NON_MEMBRO:
            await interaction.response.send_message(
                "Non fai più parte di questa gilda.", ephemeral=True
            )
            return
        if esito.stato is StatoBoost.GIA_ATTIVO:
            attivi = dict(esito.attivi)
            await interaction.response.send_message(
                _testo_boost_gia_attivo(
                    esito.attivi, attivi.get(Beneficio.EXP), attivi.get(Beneficio.COIN),
                    adesso, "Hai",
                ),
                ephemeral=True,
            )
            return
        if esito.stato is not StatoBoost.ACQUISTATO:
            await interaction.response.send_message(
                f"Non hai abbastanza coin personali — servono **{costo}**.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"✅ Boost personale {tipo_boost.value} ×{BOOST_MULTIPLIER} attivo sul tuo tick vocale "
            f"in **{clan.name}** fino a <t:{int(esito.scadenza.timestamp())}:f>."
        )

    @comando_di_gruppo(
        "clan",
        nome="gilda",
        descrizione=f"Acquista un boost ×{BOOST_MULTIPLIER} per {BOOST_DURATION_HOURS}h per TUTTI i membri, dalla tesoreria.",
        sottogruppo=_SG_BOOST,
    )
    @app_commands.describe(tipo="Cosa raddoppia: exp, coin o entrambi (super)")
    @app_commands.choices(tipo=_scelte_boost(GUILD_BOOST_COSTS))
    async def clan_boost_gilda(
        self, interaction: discord.Interaction, tipo: app_commands.Choice[str]
    ) -> None:
        guild = interaction.guild
        if await _comando_rifiutato(interaction):
            return

        clan = await guild_clan_repo.get_member_clan_in_guild(guild.id, interaction.user.id)
        if clan is None:
            await interaction.response.send_message(
                "Non fai parte di nessuna gilda in questo server.", ephemeral=True
            )
            return

        chi_acquista = await guild_clan_repo.get_member(clan.id, interaction.user.id)
        if chi_acquista is None or chi_acquista.role not in RUOLI_UFFICIALI:
            await interaction.response.send_message(
                "Solo il Capo Clan, il Co-Owner o un Admin Clan possono acquistare il boost di gilda.",
                ephemeral=True,
            )
            return

        tipo_boost = _tipo_da_scelta(tipo)
        costo = GUILD_BOOST_COSTS[tipo_boost]
        adesso = datetime.now(timezone.utc)
        esito = await guild_clan_repo.buy_guild_boost(clan.id, tipo_boost, adesso)
        if esito.stato is StatoBoost.ASSENTE:
            await interaction.response.send_message(
                "Questa gilda non esiste più.", ephemeral=True
            )
            return
        if esito.stato is StatoBoost.GIA_ATTIVO:
            attivi = dict(esito.attivi)
            await interaction.response.send_message(
                _testo_boost_gia_attivo(
                    esito.attivi, attivi.get(Beneficio.EXP), attivi.get(Beneficio.COIN),
                    adesso, "La gilda ha",
                ),
                ephemeral=True,
            )
            return
        if esito.stato is not StatoBoost.ACQUISTATO:
            gilda_aggiornata = await guild_clan_repo.get_clan(clan.id)
            saldo = gilda_aggiornata.treasury_balance if gilda_aggiornata else clan.treasury_balance
            await interaction.response.send_message(
                f"La tesoreria della gilda non basta — servono **{costo}** coin "
                f"(ne avete **{saldo}**).",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"✅ Boost di gilda {tipo_boost.value} ×{BOOST_MULTIPLIER} attivo per TUTTI i membri "
            f"di **{clan.name}** fino a <t:{int(esito.scadenza.timestamp())}:f>."
        )

    # ================================================================
    # Giveaway (SPEC.md §15.5, con requisiti di ruolo/livello)
    # ================================================================
    class GiveawayEnterView(BaseView):
        """
        PERSISTENTE (timeout=None, custom_id fisso che incorpora
        l'ID del giveaway) — un giveaway dura ore o giorni, deve
        continuare a funzionare anche dopo un riavvio del bot.
        main.py la ri-registra per ogni giveaway ancora attivo ad
        ogni avvio (bot.add_view), altrimenti i pulsanti dei
        messaggi già inviati smetterebbero di rispondere.
        """

        def __init__(self, giveaway_id: int) -> None:
            super().__init__(timeout=None)
            self._entra.custom_id = f"giveaway_enter:{giveaway_id}"
            self.giveaway_id = giveaway_id

        @discord.ui.button(label="Partecipa", emoji="🎉", style=discord.ButtonStyle.primary)
        async def _entra(
            self, interaction: discord.Interaction, button: discord.ui.Button
        ) -> None:
            giveaway = await giveaway_repo.get_giveaway(self.giveaway_id)
            if giveaway is None or giveaway.ended:
                await interaction.response.send_message(
                    "Questo giveaway non è più attivo.", ephemeral=True
                )
                return

            totali = await leveling_repo.get_totals(giveaway.guild_id, interaction.user.id)
            ruoli_utente = {r.id for r in interaction.user.roles}
            messaggi = (
                await giveaway_repo.message_count(self.giveaway_id, interaction.user.id)
                if giveaway.min_messages > 0
                else 0
            )
            salto = {giveaway.bypass_role_id} if giveaway.bypass_role_id is not None else set()
            mancanti = requisiti_mancanti(
                totali.level, ruoli_utente, giveaway.min_level, giveaway.required_role_id,
                messaggi, giveaway.min_messages, salto,
            )
            if mancanti:
                await interaction.response.send_message(
                    f"Non soddisfi i requisiti per partecipare (richiesto: {', '.join(mancanti)}).",
                    ephemeral=True,
                )
                return

            biglietti = biglietti_di(ruoli_utente, giveaway.bonus_role_id, giveaway.bonus_entries)
            nuova = await giveaway_repo.add_entry(self.giveaway_id, interaction.user.id, biglietti)
            if nuova:
                extra = f" Hai {biglietti} ingressi." if biglietti > 1 else ""
                await interaction.response.send_message(
                    f"✅ Partecipazione registrata, in bocca al lupo!{extra}", ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "Avevi già partecipato a questo giveaway.", ephemeral=True
                )

    # ================================================================
    # Impostazioni dei livelli (NF-15, #86) — /level impostazioni
    # ================================================================
    @comando_di_gruppo(
        "level",
        nome="mostra",
        descrizione="Mostra le impostazioni dei livelli di questo server.",
        sottogruppo=_SG_IMPOSTAZIONI,
    )
    @richiedi(Livello.ADMIN)
    async def impostazioni_mostra(self, interaction: discord.Interaction) -> None:
        if await _comando_rifiutato(interaction):
            return
        config = await leveling_settings_repo.get_config(interaction.guild.id)
        await interaction.response.send_message(
            embed=_embed_impostazioni(config), ephemeral=True
        )

    @comando_di_gruppo(
        "level",
        nome="annuncio",
        descrizione="Dove e quando annunciare i level-up.",
        sottogruppo=_SG_IMPOSTAZIONI,
    )
    @app_commands.describe(
        modo="Dove annunciare: spento, canale in cui scrive, messaggio privato o canale scelto",
        canale="Il canale (solo con 'canale scelto')",
        livello_minimo="Non annunciare sotto questo livello",
        ogni="Annuncia solo ogni N livelli (5 = ai livelli 5, 10, 15...)",
        solo_premi="Annuncia solo i livelli che danno un ruolo-premio",
    )
    @app_commands.choices(modo=_SCELTE_ANNUNCIO)
    @richiedi(Livello.ADMIN)
    async def impostazioni_annuncio(
        self,
        interaction: discord.Interaction,
        modo: app_commands.Choice[str] | None = None,
        canale: discord.TextChannel | None = None,
        livello_minimo: app_commands.Range[int, 0, 1000] | None = None,
        ogni: app_commands.Range[int, 1, 100] | None = None,
        solo_premi: bool | None = None,
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        campi = {}
        if modo is not None:
            campi["levelup_mode"] = modo.value
        if canale is not None:
            campi["levelup_channel_id"] = canale.id
        if livello_minimo is not None:
            campi["levelup_min_level"] = livello_minimo
        if ogni is not None:
            campi["levelup_every"] = ogni
        if solo_premi is not None:
            campi["levelup_only_rewards"] = solo_premi
        await self._salva_impostazioni(interaction, campi)

    @comando_di_gruppo(
        "level",
        nome="premi",
        descrizione="Ruoli-premio: tienili tutti o tieni solo quello più alto.",
        sottogruppo=_SG_IMPOSTAZIONI,
    )
    @app_commands.describe(modo="'accumula' li tiene tutti, 'sostituisci' toglie i precedenti")
    @app_commands.choices(modo=_SCELTE_PREMI)
    @richiedi(Livello.ADMIN)
    async def impostazioni_premi(
        self, interaction: discord.Interaction, modo: app_commands.Choice[str]
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        await self._salva_impostazioni(interaction, {"reward_mode": modo.value})

    @comando_di_gruppo(
        "level",
        nome="xp",
        descrizione="Quanti XP e coin si guadagnano, e come si sommano i moltiplicatori.",
        sottogruppo=_SG_IMPOSTAZIONI,
    )
    @app_commands.describe(
        testo="XP per ogni messaggio che conta (1-100)",
        attesa="Secondi tra due messaggi che danno XP (10-600)",
        voce_xp="XP per ogni minuto in vocale (0-50)",
        voce_coin="Coin per ogni minuto in vocale (0-50)",
        moltiplicatori="Più moltiplicatori insieme: si sommano oppure vale solo il più alto",
        daily="Coin di /level daily (0-10000)",
        lavoro_min="Coin minimi di /level work (0-10000)",
        lavoro_max="Coin massimi di /level work (0-10000)",
        livello_massimo="Livello massimo raggiungibile (0 = nessun tetto)",
    )
    @app_commands.choices(moltiplicatori=_SCELTE_MOLTIPLICATORI)
    @richiedi(Livello.ADMIN)
    async def impostazioni_xp(
        self,
        interaction: discord.Interaction,
        testo: app_commands.Range[int, 1, 100] | None = None,
        attesa: app_commands.Range[int, 10, 600] | None = None,
        voce_xp: app_commands.Range[int, 0, 50] | None = None,
        voce_coin: app_commands.Range[int, 0, 50] | None = None,
        moltiplicatori: app_commands.Choice[str] | None = None,
        daily: app_commands.Range[int, 0, 10000] | None = None,
        lavoro_min: app_commands.Range[int, 0, 10000] | None = None,
        lavoro_max: app_commands.Range[int, 0, 10000] | None = None,
        livello_massimo: app_commands.Range[int, 0, 1000] | None = None,
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        campi = {}
        if testo is not None:
            campi["text_xp"] = testo
        if attesa is not None:
            campi["text_cooldown_seconds"] = attesa
        if voce_xp is not None:
            campi["voice_xp_per_minute"] = voce_xp
        if voce_coin is not None:
            campi["voice_coins_per_minute"] = voce_coin
        if moltiplicatori is not None:
            campi["multiplier_mode"] = moltiplicatori.value
        for nome, valore in (
            ("daily_coins", daily), ("work_min", lavoro_min),
            ("work_max", lavoro_max), ("max_level", livello_massimo),
        ):
            if valore is not None:
                campi[nome] = valore
        await self._salva_impostazioni(interaction, campi)

    async def _salva_impostazioni(self, interaction: discord.Interaction, campi: dict) -> None:
        if not campi:
            await interaction.response.send_message(
                "Scegli almeno un valore da cambiare.", ephemeral=True
            )
            return
        try:
            await leveling_settings_repo.set_options(interaction.guild.id, **campi)
        except ValueError as errore:
            await interaction.response.send_message(f"❌ {errore}", ephemeral=True)
            return
        config = await leveling_settings_repo.get_config(interaction.guild.id)
        await interaction.response.send_message(
            "✅ Impostazioni salvate.", embed=_embed_impostazioni(config), ephemeral=True
        )

    @comando_di_gruppo(
        "level",
        nome="escludi",
        descrizione="Un canale, una categoria o un ruolo non dà XP (rifallo per toglierlo).",
        sottogruppo=_SG_IMPOSTAZIONI,
    )
    @app_commands.describe(
        canale="Il canale senza XP (anche vocale o forum). Una categoria vale per tutti i suoi canali",
        ruolo="Il ruolo i cui membri non prendono XP",
    )
    @richiedi(Livello.ADMIN)
    async def impostazioni_escludi(
        self,
        interaction: discord.Interaction,
        canale: discord.abc.GuildChannel | None = None,
        ruolo: discord.Role | None = None,
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        if (canale is None) == (ruolo is None):
            await interaction.response.send_message(
                "Scegli un canale oppure un ruolo, non entrambi.", ephemeral=True
            )
            return
        tipo, bersaglio = (
            ("canale_escluso", canale) if canale is not None else ("ruolo_escluso", ruolo)
        )
        config = await leveling_settings_repo.get_config(interaction.guild.id)
        gia = bersaglio.id in (
            config.canali_esclusi if canale is not None else config.ruoli_esclusi
        )
        if gia:
            await leveling_settings_repo.remove_rule(interaction.guild.id, tipo, bersaglio.id)
            testo = f"✅ {bersaglio.mention} dà di nuovo XP."
        else:
            try:
                await leveling_settings_repo.set_rule(interaction.guild.id, tipo, bersaglio.id)
            except RegolaPiena:
                await interaction.response.send_message(
                    f"❌ Hai già {MAX_REGOLE_PER_TIPO} esclusioni di questo tipo.", ephemeral=True
                )
                return
            testo = f"✅ {bersaglio.mention} non dà più XP."
        await interaction.response.send_message(testo, ephemeral=True)

    @comando_di_gruppo(
        "level",
        nome="moltiplicatore",
        descrizione="XP moltiplicati in un canale o per un ruolo (fattore 1 = toglie la regola).",
        sottogruppo=_SG_IMPOSTAZIONI,
    )
    @app_commands.describe(
        fattore="Da 0.1 a 10 (2 = XP doppi); 1 toglie la regola",
        canale="Il canale (anche vocale)",
        ruolo="Il ruolo",
    )
    @richiedi(Livello.ADMIN)
    async def impostazioni_moltiplicatore(
        self,
        interaction: discord.Interaction,
        fattore: app_commands.Range[float, FATTORE_MINIMO, FATTORE_MASSIMO],
        canale: discord.abc.GuildChannel | None = None,
        ruolo: discord.Role | None = None,
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        if (canale is None) == (ruolo is None):
            await interaction.response.send_message(
                "Scegli un canale oppure un ruolo, non entrambi.", ephemeral=True
            )
            return
        tipo, bersaglio = (
            ("mult_canale", canale) if canale is not None else ("mult_ruolo", ruolo)
        )
        if fattore == 1:
            await leveling_settings_repo.remove_rule(interaction.guild.id, tipo, bersaglio.id)
            testo = f"✅ Nessun moltiplicatore su {bersaglio.mention}."
        else:
            try:
                await leveling_settings_repo.set_rule(
                    interaction.guild.id, tipo, bersaglio.id, round(fattore, 2)
                )
            except RegolaPiena:
                await interaction.response.send_message(
                    f"❌ Hai già {MAX_REGOLE_PER_TIPO} moltiplicatori di questo tipo.",
                    ephemeral=True,
                )
                return
            testo = f"✅ XP ×{fattore:g} su {bersaglio.mention}."
        await interaction.response.send_message(testo, ephemeral=True)

    async def _avvia_giveaway(
        self,
        interaction: discord.Interaction,
        *,
        prize: str,
        durata_minuti: int,
        winners: int,
        min_level: int,
        required_role_id: int | None,
        min_messaggi: int,
        bypass_role_id: int | None,
        bonus_role_id: int | None,
        ingressi_extra: int,
        inizia_tra: int | None,
    ) -> None:
        """Crea il giveaway (subito o programmato) e risponde. Condiviso da /giveaway e dai modelli."""
        guild = interaction.guild
        if ingressi_extra > 0 and bonus_role_id is None:
            await interaction.response.send_message(
                "Gli ingressi extra servono a un ruolo: indica anche quale.", ephemeral=True
            )
            return
        adesso = datetime.now(timezone.utc)
        programmato = inizia_tra is not None
        inizio = adesso + timedelta(minutes=inizia_tra) if programmato else adesso
        scadenza = inizio + timedelta(minutes=durata_minuti)

        giveaway_id = await giveaway_repo.create_giveaway(
            guild.id, interaction.channel.id, prize, winners, min_level,
            required_role_id, scadenza, interaction.user.id,
            min_messages=min_messaggi, bypass_role_id=bypass_role_id,
            bonus_role_id=bonus_role_id, bonus_entries=ingressi_extra,
            starts_at=inizio if programmato else None,
            duration_seconds=durata_minuti * 60 if programmato else None,
        )
        if programmato:
            await interaction.response.send_message(
                f"🗓️ Giveaway programmato: parte <t:{int(inizio.timestamp())}:R> in questo canale "
                f"e dura {durata_minuti} minuti.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=titolo_giveaway(prize),
            description=descrizione_giveaway(await giveaway_repo.get_giveaway(giveaway_id)),
            color=discord.Color.blurple(),
        )
        view = self.GiveawayEnterView(giveaway_id)
        await interaction.response.send_message(embed=embed, view=view)
        messaggio = await interaction.original_response()
        await giveaway_repo.set_message_id(giveaway_id, messaggio.id)

    @comando_di_gruppo(
        "gestione",
        nome="giveaway",
        descrizione="Avvia un giveaway.",
        sottogruppo=_SG_ECONOMIA,
    )
    @app_commands.describe(
        prize="Cosa si vince",
        duration_minutes="Durata in minuti",
        winners="Numero di vincitori (default 1)",
        min_level="Livello minimo richiesto (facoltativo)",
        required_role="Ruolo richiesto per partecipare (facoltativo)",
        min_messaggi="Messaggi da scrivere dopo la partenza del giveaway (facoltativo)",
        ruolo_bypass="Chi ha questo ruolo salta i requisiti (facoltativo)",
        ruolo_extra="Ruolo che ha più ingressi (facoltativo)",
        ingressi_extra="Ingressi in più per chi ha il ruolo extra",
        inizia_tra="Programma la partenza tra tanti minuti (facoltativo)",
    )
    async def giveaway(
        self,
        interaction: discord.Interaction,
        prize: app_commands.Range[str, 1, MAX_PREMIO_GIVEAWAY],
        duration_minutes: app_commands.Range[int, 1, 43200],
        winners: app_commands.Range[int, 1, 50] = 1,
        min_level: app_commands.Range[int, 0, 1000] = 0,
        required_role: discord.Role | None = None,
        min_messaggi: app_commands.Range[int, 0, MAX_MESSAGGI_RICHIESTI] = 0,
        ruolo_bypass: discord.Role | None = None,
        ruolo_extra: discord.Role | None = None,
        ingressi_extra: app_commands.Range[int, 0, MAX_INGRESSI_EXTRA] = 0,
        inizia_tra: app_commands.Range[int, 1, 43200] | None = None,
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        if interaction.guild is None or interaction.channel is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return
        await self._avvia_giveaway(
            interaction, prize=prize, durata_minuti=duration_minutes, winners=winners,
            min_level=min_level, required_role_id=required_role.id if required_role else None,
            min_messaggi=min_messaggi, bypass_role_id=ruolo_bypass.id if ruolo_bypass else None,
            bonus_role_id=ruolo_extra.id if ruolo_extra else None,
            ingressi_extra=ingressi_extra, inizia_tra=inizia_tra,
        )

    @comando_di_gruppo(
        "gestione",
        nome="giveaway-modello",
        descrizione="Modelli di giveaway: salva, elenca, elimina o avvia.",
        sottogruppo=_SG_ECONOMIA,
    )
    @app_commands.describe(
        azione="Cosa fare",
        nome="Nome del modello (serve per salva, elimina e avvia)",
        premio="Cosa si vince (per salva)",
        vincitori="Numero di vincitori (per salva)",
        durata_minuti="Durata in minuti (per salva)",
        min_livello="Livello minimo (per salva)",
        ruolo_richiesto="Ruolo richiesto (per salva)",
        min_messaggi="Messaggi richiesti dopo la partenza (per salva)",
        ruolo_bypass="Ruolo che salta i requisiti (per salva)",
        ruolo_extra="Ruolo con più ingressi (per salva)",
        ingressi_extra="Ingressi in più per il ruolo extra (per salva)",
        inizia_tra="Programma la partenza tra tanti minuti (per avvia)",
    )
    @app_commands.choices(azione=_SCELTE_AZIONE_MODELLO)
    async def giveaway_modello(
        self,
        interaction: discord.Interaction,
        azione: app_commands.Choice[str],
        nome: app_commands.Range[str, 1, 32] | None = None,
        premio: app_commands.Range[str, 1, MAX_PREMIO_GIVEAWAY] | None = None,
        vincitori: app_commands.Range[int, 1, 50] | None = None,
        durata_minuti: app_commands.Range[int, 1, 43200] | None = None,
        min_livello: app_commands.Range[int, 0, 1000] | None = None,
        ruolo_richiesto: discord.Role | None = None,
        min_messaggi: app_commands.Range[int, 0, MAX_MESSAGGI_RICHIESTI] | None = None,
        ruolo_bypass: discord.Role | None = None,
        ruolo_extra: discord.Role | None = None,
        ingressi_extra: app_commands.Range[int, 0, MAX_INGRESSI_EXTRA] | None = None,
        inizia_tra: app_commands.Range[int, 1, 43200] | None = None,
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        if interaction.guild is None or interaction.channel is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return
        guild_id = interaction.guild.id
        cosa = azione.value

        if cosa == "elenco":
            modelli = await giveaway_repo.list_templates(guild_id)
            if not modelli:
                await interaction.response.send_message("Nessun modello salvato.", ephemeral=True)
                return
            righe = [
                taglia(f"• **{m.name}** — {m.prize}, {m.winners_count} vincitori, {m.duration_minutes} min", 120)
                for m in modelli
            ]
            await interaction.response.send_message("\n".join(righe), ephemeral=True)
            return

        if nome is None:
            await interaction.response.send_message("Indica il nome del modello.", ephemeral=True)
            return

        if cosa == "elimina":
            tolto = await giveaway_repo.delete_template(guild_id, nome)
            await interaction.response.send_message(
                "✅ Modello eliminato." if tolto else "Questo modello non esiste.", ephemeral=True
            )
            return

        if cosa == "salva":
            if premio is None or durata_minuti is None:
                await interaction.response.send_message(
                    "Per salvare servono almeno il premio e la durata.", ephemeral=True
                )
                return
            if ingressi_extra and ruolo_extra is None:
                await interaction.response.send_message(
                    "Gli ingressi extra servono a un ruolo: indica anche quale.", ephemeral=True
                )
                return
            try:
                await giveaway_repo.save_template(
                    guild_id, nome, prize=premio, winners_count=vincitori or 1,
                    duration_minutes=durata_minuti, min_level=min_livello or 0,
                    required_role_id=ruolo_richiesto.id if ruolo_richiesto else None,
                    min_messages=min_messaggi or 0,
                    bypass_role_id=ruolo_bypass.id if ruolo_bypass else None,
                    bonus_role_id=ruolo_extra.id if ruolo_extra else None,
                    bonus_entries=ingressi_extra or 0,
                )
            except ModelloPieno:
                await interaction.response.send_message(
                    "Ci sono già 25 modelli: eliminane uno prima.", ephemeral=True
                )
                return
            await interaction.response.send_message(f"✅ Modello **{nome}** salvato.", ephemeral=True)
            return

        modello = await giveaway_repo.get_template(guild_id, nome)  # cosa == "avvia"
        if modello is None:
            await interaction.response.send_message("Questo modello non esiste.", ephemeral=True)
            return
        await self._avvia_giveaway(
            interaction, prize=modello.prize, durata_minuti=modello.duration_minutes,
            winners=modello.winners_count, min_level=modello.min_level,
            required_role_id=modello.required_role_id, min_messaggi=modello.min_messages,
            bypass_role_id=modello.bypass_role_id, bonus_role_id=modello.bonus_role_id,
            ingressi_extra=modello.bonus_entries, inizia_tra=inizia_tra,
        )

async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_LEVELING,
            display_name="Livelli & Economia",
            category="leveling",
            description="XP, livelli, daily/work/pay, classifiche mensili e all-time.",
            premium_capable=False,
        )
    )
    # Gli inviti in gilda devono funzionare anche dopo un riavvio.
    bot.add_dynamic_items(BottoneInvitoClan)
    await bot.add_cog(LevelingCog(bot))
