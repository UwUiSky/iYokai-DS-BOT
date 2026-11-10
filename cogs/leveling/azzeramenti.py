"""
cogs/leveling/azzeramenti.py
============================
/admin-livelli azzera (server, ripristina, auto), /admin-livelli diagnosi. Azzera gli XP di tutto il
server dopo aver scritto il nome del server, con copia di sicurezza di 30 giorni e ripristino; azzera
chi esce o viene bannato; blocca gli XP a mano e gli azzeramenti al proprietario; spiega perché un
membro non prende XP.
Funzioni coperte: SPEC §15 (LIV-068, 069, 070, 071, 075; catalogo #124)
Dipende da: core/leveling_azzera_logic.py, core/repositories/leveling_copie_repo.py
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from cogs.leveling._pagine import taglia
from cogs.leveling.leveling import MODULE_LEVELING, _comando_rifiutato
from core.bounded_cache import BoundedCache
from core.command_groups import SOTTOGRUPPI, CogConGruppi, comando_di_gruppo, togli_comandi_del_cog
from core.database import db
from core.i18n import testo_per
from core.leveling_azzera_logic import (
    MAX_MOTIVO,
    MAX_NOME_SERVER,
    SECONDI_ATTESA_BAN,
    deve_azzerare,
    diagnosi_xp,
    nome_confermato,
    rifiutato_dal_blocco,
)
from core.leveling_logic import id_canali_per_le_regole
from core.repositories.blacklist_repo import blacklist_repo
from core.repositories.leveling_copie_repo import leveling_copie_repo
from core.repositories.leveling_repo import leveling_repo
from core.repositories.leveling_settings_repo import leveling_settings_repo
from core.ui_base import BaseModal, BaseView

logger = logging.getLogger("iyokai.leveling.azzeramenti")

SECONDI_VALIDITA_BAN = 60  # un ban conta come ban per l'uscita che arriva subito prima o dopo, non per sempre

_SG = SOTTOGRUPPI["admin-livelli azzera"]
_SCELTE_AZZERA_SU = [
    app_commands.Choice(name="Nessuno", value="nessuno"),
    app_commands.Choice(name="Chi esce o viene espulso", value="uscita"),
    app_commands.Choice(name="Chi viene bannato", value="ban"),
    app_commands.Choice(name="Uscita e ban", value="entrambi"),
]


async def _puo_gestire(interaction: discord.Interaction) -> bool:
    """Ricontrollo al momento dell'azione: il permesso può cambiare dopo il comando."""
    if interaction.permissions.manage_guild:
        return True
    await _rispondi(interaction, await testo_per(interaction, "azz_serve_gestire_server"))
    return False


async def _rispondi(interaction: discord.Interaction, testo: str) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(testo, ephemeral=True)
    else:
        await interaction.response.send_message(testo, ephemeral=True)


async def _bloccato(interaction: discord.Interaction, voce: str) -> bool:
    """
    LIV-071: True (con risposta già data) se `voce` («blocca_xp» o «blocca_azzeramento») è accesa
    e chi agisce non è il proprietario del server. Legge le impostazioni al momento, non dalla cache.
    """
    i = (await leveling_settings_repo.get_config(interaction.guild.id, fresco=True)).impostazioni
    if rifiutato_dal_blocco(getattr(i, voce), interaction.user.id, interaction.guild.owner_id):
        await _rispondi(interaction, await testo_per(interaction, "azz_solo_proprietario"))
        return True
    return False


def _data(momento: datetime) -> str:
    return f"<t:{int(momento.timestamp())}:d>"


_LAVORI: set[asyncio.Task] = set()


def _avvia_sincronia(bot, guild: discord.Guild, user_ids) -> None:
    """Ricontrolla i ruoli-premio dopo un azzeramento o un ripristino, senza far aspettare il comando."""
    livelli = bot.get_cog("LevelingCog") if bot is not None else None
    if livelli is None:
        return
    lavoro = asyncio.create_task(livelli.sincronizza_server(guild, user_ids))
    _LAVORI.add(lavoro)
    lavoro.add_done_callback(_LAVORI.discard)


class ModaleAzzeraServer(BaseModal):
    """Il nome del server scritto a mano: nessun clic distratto azzera tutto."""

    def __init__(self, titolo: str, etichetta_nome: str, etichetta_motivo: str) -> None:
        super().__init__(title=titolo[:45], timeout=600)
        self._usato = False
        self.nome = discord.ui.TextInput(max_length=MAX_NOME_SERVER, min_length=1, required=True)
        self.motivo = discord.ui.TextInput(
            style=discord.TextStyle.paragraph, max_length=MAX_MOTIVO, required=False,
        )
        self.add_item(discord.ui.Label(text=etichetta_nome[:45], component=self.nome))
        self.add_item(discord.ui.Label(text=etichetta_motivo[:45], component=self.motivo))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if self._usato:  # nessun await prima del segno: due invii non passano insieme
            return
        self._usato = True
        guild = interaction.guild
        if guild is None or not await db.is_module_active_for_guild(guild.id, MODULE_LEVELING):
            await _rispondi(interaction, await testo_per(interaction, "leveling_questo_modulo_non_attivo_su"))
            return
        if not await _puo_gestire(interaction) or await _bloccato(interaction, "blocca_azzeramento"):
            return
        if not nome_confermato(self.nome.value, guild.name):
            await _rispondi(interaction, await testo_per(interaction, "azz_nome_sbagliato", nome=taglia(guild.name, 100)))
            return
        await interaction.response.defer(ephemeral=True)
        esito = await leveling_copie_repo.azzera_server(guild.id, interaction.user.id, self.motivo.value or "")
        if esito is None:
            await interaction.followup.send(await testo_per(interaction, "azz_niente_da_azzerare"), ephemeral=True)
            return
        logger.info(
            "XP del server azzerati: server %s, staff %s, %s persone, copia %s.",
            guild.id, interaction.user.id, esito.utenti, esito.copia_id,
        )
        await interaction.followup.send(
            await testo_per(interaction, "azz_server_azzerato", utenti=esito.utenti, copia=esito.copia_id),
            ephemeral=True,
        )
        # LIV-043: i ruoli-premio seguono i nuovi livelli (a lotti, in sottofondo).
        _avvia_sincronia(interaction.client, guild, await leveling_copie_repo.ids_copia(guild.id, esito.copia_id))


class ConfermaRipristinoView(BaseView):
    """«Ripristinare?»: solo chi ha dato il comando; vale una volta sola; ricontrolla al clic."""

    def __init__(self, autore_id: int, copia_id: int) -> None:
        super().__init__(timeout=120)
        self.autore_id = autore_id
        self.copia_id = copia_id
        self._usata = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        if interaction.user.id != self.autore_id:
            await interaction.response.send_message(
                await testo_per(interaction, "leveling_solo_chi_ha_usato_il"), ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Ripristina", style=discord.ButtonStyle.danger)
    async def conferma(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._usata:
            await interaction.response.send_message(await testo_per(interaction, "leveling_gia_fatto"), ephemeral=True)
            return
        self._usata = True
        self.stop()
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if guild is None or not await db.is_module_active_for_guild(guild.id, MODULE_LEVELING):
            await _rispondi(interaction, await testo_per(interaction, "leveling_questo_modulo_non_attivo_su"))
            return
        if not await _puo_gestire(interaction) or await _bloccato(interaction, "blocca_azzeramento"):
            return
        persone = await leveling_copie_repo.ripristina(guild.id, self.copia_id)
        if persone is None:
            await interaction.followup.send(await testo_per(interaction, "azz_nessuna_copia"), ephemeral=True)
            return
        logger.info("XP ripristinati: server %s, staff %s, copia %s.", guild.id, interaction.user.id, self.copia_id)
        await interaction.followup.send(
            await testo_per(interaction, "azz_ripristinato", utenti=persone, copia=self.copia_id), ephemeral=True
        )
        _avvia_sincronia(interaction.client, guild, await leveling_copie_repo.ids_copia(guild.id, self.copia_id))
        try:
            await interaction.edit_original_response(view=None)
        except discord.HTTPException:
            pass

    @discord.ui.button(label="Annulla", style=discord.ButtonStyle.secondary)
    async def annulla(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self._usata = True
        self.stop()
        await interaction.response.edit_message(content=await testo_per(interaction, "azz_annullato"), view=None)


class AzzeramentiCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Chi è stato bannato da poco: «uscita» non deve contare anche i ban.
        self._bannati: BoundedCache[tuple[int, int], float] = BoundedCache(max_size=500)

    def cog_unload(self) -> None:
        togli_comandi_del_cog(self)

    # ---------------------------------------------------------------- LIV-068
    @comando_di_gruppo(
        "admin-livelli",
        nome="server",
        descrizione="Azzera gli XP di tutto il server (prima fa una copia di sicurezza).",
        sottogruppo=_SG,
    )
    async def azzera_server(self, interaction: discord.Interaction) -> None:
        if await _comando_rifiutato(interaction):
            return
        if not await _puo_gestire(interaction) or await _bloccato(interaction, "blocca_azzeramento"):
            return
        modale = ModaleAzzeraServer(
            await testo_per(interaction, "azz_modale_titolo"),
            await testo_per(interaction, "azz_modale_nome"),
            await testo_per(interaction, "azz_modale_motivo"),
        )
        await interaction.response.send_modal(modale)

    # ---------------------------------------------------------------- LIV-069
    async def _scelte_copie(self, interaction: discord.Interaction, scritto: str) -> list[app_commands.Choice[str]]:
        if interaction.guild is None:
            return []
        scelte = []
        for c in await leveling_copie_repo.elenco(interaction.guild.id):
            nome = f"#{c.id} · {c.tipo} · {c.righe} · {c.creata_il:%d/%m/%Y %H:%M}"
            if scritto.strip() in nome:
                scelte.append(app_commands.Choice(name=nome[:100], value=str(c.id)))
        return scelte[:25]

    @comando_di_gruppo(
        "admin-livelli",
        nome="ripristina",
        descrizione="Rimette gli XP di una copia di sicurezza (valida 30 giorni).",
        sottogruppo=_SG,
    )
    @app_commands.describe(copia="La copia da rimettere")
    @app_commands.autocomplete(copia=_scelte_copie)
    async def azzera_ripristina(self, interaction: discord.Interaction, copia: app_commands.Range[str, 1, 20]) -> None:
        if await _comando_rifiutato(interaction):
            return
        if not await _puo_gestire(interaction) or await _bloccato(interaction, "blocca_azzeramento"):
            return
        trovata = await leveling_copie_repo.get(interaction.guild.id, int(copia)) if copia.isdigit() and len(copia) < 19 else None
        if trovata is None:
            await interaction.response.send_message(await testo_per(interaction, "azz_nessuna_copia"), ephemeral=True)
            return
        await interaction.response.send_message(
            await testo_per(
                interaction, "azz_ripristina_chiedi", copia=trovata.id, tipo=trovata.tipo,
                utenti=trovata.righe, data=_data(trovata.creata_il),
            ),
            view=ConfermaRipristinoView(interaction.user.id, trovata.id),
            ephemeral=True,
        )

    # ---------------------------------------------------------------- LIV-070 e 071
    @comando_di_gruppo(
        "admin-livelli",
        nome="auto",
        descrizione="Azzera chi esce o viene bannato; blocca XP e azzeramenti al proprietario.",
        sottogruppo=_SG,
    )
    @app_commands.describe(
        azzera_su="Quando azzerare gli XP di una persona",
        copia="Tieni 30 giorni una copia degli XP azzerati (di base no)",
        blocca_xp="Gli XP a mano (/admin-livelli membro) solo al proprietario del server",
        blocca_azzeramento="Azzerare e ripristinare solo il proprietario del server",
    )
    @app_commands.choices(azzera_su=_SCELTE_AZZERA_SU)
    async def azzera_auto(
        self,
        interaction: discord.Interaction,
        azzera_su: app_commands.Choice[str] | None = None,
        copia: bool | None = None,
        blocca_xp: bool | None = None,
        blocca_azzeramento: bool | None = None,
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        if not await _puo_gestire(interaction) or await _bloccato(interaction, "blocca_azzeramento"):
            return
        campi = {}
        if azzera_su is not None:
            campi["azzera_su"] = azzera_su.value
        if copia is not None:
            campi["copia_su_uscita"] = copia
        if blocca_xp is not None:
            campi["blocca_xp"] = blocca_xp
        if blocca_azzeramento is not None:
            campi["blocca_azzeramento"] = blocca_azzeramento
        if not campi:
            await interaction.response.send_message(
                await testo_per(interaction, "leveling_scegli_almeno_un_valore_da"), ephemeral=True
            )
            return
        # Con un blocco già acceso gli interruttori li cambia solo il proprietario.
        if ("blocca_xp" in campi or "blocca_azzeramento" in campi) and await _bloccato(interaction, "blocca_xp"):
            return
        await leveling_settings_repo.set_options(interaction.guild.id, **campi)
        logger.info("Azzeramenti automatici cambiati: server %s, staff %s, %s.", interaction.guild.id, interaction.user.id, campi)
        i = (await leveling_settings_repo.get_config(interaction.guild.id)).impostazioni
        si, no = await testo_per(interaction, "azz_si"), await testo_per(interaction, "azz_no")
        await interaction.response.send_message(
            await testo_per(
                interaction, "azz_auto_salvato",
                azzera=await testo_per(interaction, f"azz_su_{i.azzera_su}"),
                copia=si if i.copia_su_uscita else no,
                bxp=si if i.blocca_xp else no,
                baz=si if i.blocca_azzeramento else no,
            ),
            ephemeral=True,
        )

    async def _azzera_chi_se_ne_va(self, guild: discord.Guild, utente, evento: str) -> None:
        """Se il bot si riavvia durante l'attesa di «uscita» (3 s), quell'azzeramento si perde: è accettato."""
        if getattr(utente, "bot", False):
            return
        try:
            i = (await leveling_settings_repo.get_config(guild.id)).impostazioni
            if not deve_azzerare(i.azzera_su, evento):
                return
            if evento == "uscita" and i.azzera_su == "uscita":
                # Un ban manda prima o dopo anche l'uscita: si aspetta e si guarda se è un ban.
                await asyncio.sleep(SECONDI_ATTESA_BAN)
                quando = self._bannati.get((guild.id, utente.id))
                if quando is not None and time.monotonic() - quando <= SECONDI_VALIDITA_BAN:
                    return
            if not await db.is_module_active_for_guild(guild.id, MODULE_LEVELING):
                return
            if await leveling_copie_repo.azzera_utente(guild.id, utente.id, i.copia_su_uscita, evento):
                logger.info("XP azzerati (%s): server %s, utente %s.", evento, guild.id, utente.id)
        except Exception:
            logger.warning("XP non azzerati (%s) per %s nel server %s.", evento, utente.id, guild.id, exc_info=True)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        await self._azzera_chi_se_ne_va(member.guild, member, "uscita")

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.abc.User) -> None:
        self._bannati.set((guild.id, user.id), time.monotonic())
        await self._azzera_chi_se_ne_va(guild, user, "ban")

    # ---------------------------------------------------------------- LIV-075
    @comando_di_gruppo(
        "admin-livelli",
        nome="diagnosi",
        descrizione="Spiega perché un membro non prende XP in un canale.",
    )
    @app_commands.describe(membro="Il membro", canale="Il canale (di base quello in cui scrivi)")
    async def diagnosi(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        canale: discord.abc.GuildChannel | None = None,
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        canale = canale or interaction.channel
        config = await leveling_settings_repo.get_config(guild.id)
        imp = config.impostazioni
        ultima = await leveling_repo.ultimo_xp_testo(guild.id, membro.id)
        attesa = 0
        if ultima is not None:
            attesa = imp.text_cooldown_seconds - int((datetime.now(timezone.utc) - ultima).total_seconds())
        totali = await leveling_repo.get_totals(guild.id, membro.id)
        ruoli = {r.id for r in getattr(membro, "roles", [])}
        verifiche = diagnosi_xp(
            modulo_attivo=await db.is_module_active_for_guild(guild.id, MODULE_LEVELING),
            in_blacklist=await blacklist_repo.is_user_blacklisted(membro.id),
            e_bot=membro.bot,
            canale_escluso=bool(canale and any(c in config.canali_esclusi for c in id_canali_per_le_regole(canale))),
            ruolo_escluso=bool(ruoli & config.ruoli_esclusi),
            attesa_secondi=attesa,
            livello=totali.level,
            max_level=imp.max_level,
        )
        righe = []
        for v in verifiche:
            chiave = f"azz_diag_{v.chiave}_{'ok' if v.ok else 'no'}"
            righe.append(("✅ " if v.ok else "❌ ") + await testo_per(interaction, chiave, valore=v.valore))
        problemi = sum(not v.ok for v in verifiche)
        chiusura = await testo_per(
            interaction, "azz_diag_tutto_ok" if not problemi else "azz_diag_ostacoli", n=problemi
        )
        embed = discord.Embed(
            title=taglia(await testo_per(interaction, "azz_diag_titolo", nome=membro.display_name), 256),
            description=taglia("\n".join(righe) + "\n\n" + chiusura, 4000),
            color=discord.Color.red() if problemi else discord.Color.green(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AzzeramentiCog(bot))
