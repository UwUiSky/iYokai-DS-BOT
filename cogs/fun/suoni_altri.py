"""
cogs/fun/suoni_altri.py
=======================
Suoni delle soundboard di altri server (D127, D129): `/music suono-altri` mostra un menu con l'anteprima testuale (nome,
emoji, server d'origine solo se è pubblico), il bottone «Ascolta in anteprima» (il file, solo a chi lo chiede) e il
bottone «Invia» (il suono parte nel canale vocale di chi lo preme, con lo stesso percorso di `/music suono`).
`/admin-musica suono-condividi` sceglie se i suoni del server si possono usare altrove (di base no) e se i suoi
membri possono usare quelli degli altri (di base sì). Pausa e tetto orario per persona.
Funzioni coperte: SPEC §23 (FUN-075)
Dipende da: cogs/fun/soundboard.py (suona), core/suoni_altri_logic.py, core/repositories/suoni_condivisi_repo.py
"""

from __future__ import annotations

import io
import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from core import suoni_altri_logic as logica
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.i18n import testo_per
from core.music_settings_logic import channel_not_allowed, load_music_settings
from core.repositories.suoni_condivisi_repo import suoni_condivisi_repo
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.suoni_altri")
NESSUNA_MENZIONE = discord.AllowedMentions.none()
SCADENZA_SECONDI = 180
MODULO_MUSICA = "music"


def raccogli(bot, guild: discord.Guild) -> tuple[list[logica.SuonoAltro], dict[str, object]]:
    """I suoni degli altri server che il bot vede (cache di Discord), con i loro oggetti. Solo lettura."""
    elenco: list[logica.SuonoAltro] = []
    oggetti: dict[str, object] = {}
    for s in list(getattr(bot, "soundboard_sounds", []) or []):
        origine = getattr(s, "guild", None)
        if origine is None or origine.id == guild.id or not getattr(s, "available", True):
            continue
        suono = logica.SuonoAltro(
            s.id, str(s.name)[:100], str(s.emoji) if getattr(s, "emoji", None) else None, origine.id,
            str(getattr(origine, "name", "") or ""), logica.server_pubblico(getattr(origine, "features", ()) or ()),
        )
        elenco.append(suono)
        oggetti[suono.valore] = s
    return elenco, oggetti


class SuoniAltriView(BaseView):
    """Menu dei suoni di altri server: scelta, anteprima testuale, «Ascolta in anteprima» e «Invia». Solo di chi l'ha aperto."""

    def __init__(self, cog: "SuoniAltriCog", autore_id: int, guild_id: int, suoni: list[logica.SuonoAltro], oggetti: dict, testi: dict) -> None:
        super().__init__(timeout=SCADENZA_SECONDI)
        self.cog = cog
        self.autore_id = autore_id
        self.guild_id = guild_id
        self.suoni = suoni
        self.oggetti = oggetti
        self.testi = testi
        self.scelto: logica.SuonoAltro | None = None
        self.messaggio: discord.Interaction | None = None
        self.menu.options = [
            discord.SelectOption(label=s.etichetta, value=s.valore, description=(s.origine() or testi["privato"])[:100])
            for s in suoni
        ]
        self.anteprima.disabled = self.invia.disabled = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.autore_id:
            await interaction.response.send_message(self.testi["non_tuo"], ephemeral=True)
            return False
        return await super().interaction_check(interaction)

    async def on_timeout(self) -> None:
        for voce in self.children:
            voce.disabled = True
        if self.messaggio is not None:
            try:
                await self.messaggio.edit_original_response(view=self)
            except discord.HTTPException:
                pass

    def embed(self) -> discord.Embed:
        t = self.testi
        if self.scelto is None:
            return discord.Embed(title=t["titolo"], description=t["scegli"], color=discord.Color.blurple())
        s = self.scelto
        embed = discord.Embed(title=t["titolo"], color=discord.Color.blurple())
        embed.add_field(name=t["nome"], value=s.etichetta, inline=False)
        embed.add_field(name=t["origine"], value=s.origine() or t["privato"], inline=False)
        embed.set_footer(text=t["piede"])
        return embed

    @discord.ui.select(placeholder="…", min_values=1, max_values=1, options=[discord.SelectOption(label="-", value="-")])
    async def menu(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
        self.scelto = logica.trova(self.suoni, select.values[0])
        self.anteprima.disabled = self.invia.disabled = self.scelto is None
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="Ascolta in anteprima", style=discord.ButtonStyle.secondary, emoji="🎧")
    async def anteprima(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cog.anteprima(interaction, self)

    @discord.ui.button(label="Invia", style=discord.ButtonStyle.primary, emoji="🔊")
    async def invia(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cog.invia(interaction, self)


class SuoniAltriCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.tetto = logica.TettoPersona()

    async def _regole_server(self, interaction: discord.Interaction) -> str | None:
        """None se il server può usare i suoni degli altri; altrimenti la chiave del testo che spiega perché no."""
        guild = interaction.guild
        if guild is None:
            return "guild_only_command"
        if not await db.is_module_active_for_guild(guild.id, MODULO_MUSICA):
            return "ping_questo_modulo_non_attivo_su"
        _, usa_esterni = await suoni_condivisi_repo.leggi(guild.id)
        return None if usa_esterni else "suoni_altri_server_no"

    async def _testi(self, interaction: discord.Interaction) -> dict[str, str]:
        chiavi = {"titolo": "suoni_altri_titolo", "scegli": "suoni_altri_scegli", "nome": "suoni_altri_nome",
                  "origine": "suoni_altri_origine", "privato": "suoni_altri_privato", "piede": "suoni_altri_piede",
                  "non_tuo": "suoni_altri_non_tuo"}
        return {k: await testo_per(interaction, v) for k, v in chiavi.items()}

    async def _candidati(self, guild: discord.Guild, cerca: str):
        elenco, oggetti = raccogli(self.bot, guild)
        condivisi = await suoni_condivisi_repo.server_che_condividono(list({s.guild_id for s in elenco}))
        return logica.candidati(elenco, guild.id, condivisi, cerca), oggetti

    @comando_di_gruppo("music", nome="suono-altri", descrizione="Scegli un suono dalle soundboard di altri server e mandalo in vocale.")
    @app_commands.describe(cerca="Una parte del nome del suono (massimo 50 caratteri)")
    async def suono_altri(self, interaction: discord.Interaction, cerca: Optional[app_commands.Range[str, 1, logica.MAX_CERCA]] = None) -> None:
        motivo = await self._regole_server(interaction)
        if motivo:
            await interaction.response.send_message(await testo_per(interaction, motivo), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        suoni, oggetti = await self._candidati(interaction.guild, cerca or "")
        if not suoni:
            await interaction.followup.send(await testo_per(interaction, "suoni_altri_nessuno"), ephemeral=True)
            return
        vista = SuoniAltriView(self, interaction.user.id, interaction.guild.id, suoni, oggetti, await self._testi(interaction))
        vista.messaggio = interaction
        await interaction.followup.send(embed=vista.embed(), view=vista, ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)

    async def _ancora_ammesso(self, interaction: discord.Interaction, vista: SuoniAltriView) -> object | None:
        """Ricontrolla al clic: il server d'origine può aver tolto la condivisione e il nostro può aver chiuso l'uso."""
        motivo = await self._regole_server(interaction)
        if motivo:
            await interaction.followup.send(await testo_per(interaction, motivo), ephemeral=True)
            return None
        scelto = vista.scelto
        _, oggetti = raccogli(self.bot, interaction.guild)
        oggetto = oggetti.get(scelto.valore) if scelto is not None else None
        if oggetto is None or scelto.guild_id not in await suoni_condivisi_repo.server_che_condividono([scelto.guild_id]):
            await interaction.followup.send(await testo_per(interaction, "suoni_altri_non_piu"), ephemeral=True)
            return None
        return oggetto

    async def _tetto(self, interaction: discord.Interaction) -> bool:
        blocco = self.tetto.controlla(interaction.user.id)
        if blocco is None:
            return True
        chiave = "suoni_altri_pausa" if blocco[0] == "pausa" else "suoni_altri_tetto"
        await interaction.followup.send(await testo_per(interaction, chiave, secondi=int(blocco[1]) + 1, minuti=int(blocco[1] // 60) + 1), ephemeral=True)
        return False

    async def anteprima(self, interaction: discord.Interaction, vista: SuoniAltriView) -> None:
        """Il file del suono, solo a chi lo chiede (nessun salvataggio su disco)."""
        await interaction.response.defer(ephemeral=True)
        oggetto = await self._ancora_ammesso(interaction, vista)
        if oggetto is None or not await self._tetto(interaction):
            return
        self.tetto.segna(interaction.user.id)
        try:
            dati = await oggetto.read()
        except (discord.HTTPException, OSError):
            dati = None
        if not dati:
            await interaction.followup.send(await testo_per(interaction, "suoni_altri_file_no", link=getattr(oggetto, "url", "")), ephemeral=True)
            return
        await interaction.followup.send(
            await testo_per(interaction, "suoni_altri_file", nome=vista.scelto.etichetta),
            file=discord.File(io.BytesIO(dati), filename=f"suono-{vista.scelto.id}.mp3"), ephemeral=True, allowed_mentions=NESSUNA_MENZIONE,
        )

    async def invia(self, interaction: discord.Interaction, vista: SuoniAltriView) -> None:
        """Il suono parte nel canale vocale di chi preme, dal bot musicale del canale (stesso percorso di `/music suono`)."""
        sound = self.bot.get_cog("SoundboardCog")
        musica = self.bot.get_cog("MusicCog")
        if sound is None or musica is None:
            await interaction.response.send_message(await testo_per(interaction, "soundboard_la_musica_non_disponibile_ora"), ephemeral=True)
            return
        if not await musica._controlli_base(interaction):
            return
        utente = interaction.user
        canale = utente.voice.channel
        permessi = canale.permissions_for(utente)
        if not (permessi.speak and permessi.use_soundboard and permessi.use_external_sounds):
            await interaction.response.send_message(await testo_per(interaction, "suoni_altri_permesso"), ephemeral=True)
            return
        rifiuto = channel_not_allowed(canale.id, await load_music_settings(db, interaction.guild.id))
        if rifiuto:
            await interaction.response.send_message(rifiuto, ephemeral=True)
            return
        resta = sound.pausa.resta(interaction.guild.id, utente.id)
        if resta > 0:
            await interaction.response.send_message(await testo_per(interaction, "soundboard_aspetta_ancora_secondi_prima_del", v1=int(resta) + 1), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        oggetto = await self._ancora_ammesso(interaction, vista)
        if oggetto is None or not await self._tetto(interaction):
            return
        self.tetto.segna(utente.id)
        sound.pausa.segna(interaction.guild.id, utente.id)
        testo = await sound.suona(musica, interaction, canale.id, oggetto)
        await interaction.followup.send(testo.replace("{nome}", vista.scelto.nome), ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)

    @comando_di_gruppo("admin-musica", nome="suono-condividi", descrizione="Scegli se i suoni del server si usano in altri server e viceversa.")
    @app_commands.describe(
        condividi="Gli altri server possono usare i suoni della tua soundboard (di base no)",
        usa_esterni="I tuoi membri possono usare i suoni di altri server (di base sì)",
    )
    @app_commands.rename(usa_esterni="usa-esterni")
    async def suono_condividi(
        self, interaction: discord.Interaction, condividi: Optional[bool] = None, usa_esterni: Optional[bool] = None
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return
        cond, usa = await suoni_condivisi_repo.imposta(interaction.guild.id, condividi, usa_esterni)
        testo = await testo_per(
            interaction, "suoni_altri_stato",
            condividi=await testo_per(interaction, "suoni_altri_si" if cond else "suoni_altri_no"),
            usa=await testo_per(interaction, "suoni_altri_si" if usa else "suoni_altri_no"),
        )
        await interaction.response.send_message(testo[:2000], ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SuoniAltriCog(bot))
