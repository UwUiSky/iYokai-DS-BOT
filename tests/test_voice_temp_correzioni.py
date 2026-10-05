"""
tests/test_voice_temp_correzioni.py
===================================
Correzioni ai vocali temporanei (issue #63, voci M 7.x).

Database vero (clean_db) e repository vero. I canali si creano con il
codice di produzione (`_create_temp_channel`, lo stesso del canale
generatore e del pannello); di Discord ci sono solo i finti fedeli di
tests/support/discord_fakes.py.
"""

import asyncio
from unittest.mock import MagicMock, create_autospec

import discord
import pytest
from discord.ext import commands

import cogs.voice_temp.voice_temp as modulo
import core.channel_rename as rinomina
from cogs.voice_temp.voice_temp import VoiceTempCog, _create_temp_channel
from core.repositories.voice_temp_repo import voice_temp_repo
from tests.support.discord_fakes import (
    fake_guild,
    fake_interaction,
    fake_member,
    fake_role,
    fake_voice_channel,
)

ID_SERVER = 100
ID_PROPRIETARIO = 10
ID_OSPITE = 20


@pytest.fixture(autouse=True)
def _ambiente(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    rinomina.rename_tracker._renames.clear()
    yield
    rinomina.rename_tracker._renames.clear()
    database_module.db._modules_cache.clear()


def _errore_http(stato: int = 400) -> discord.HTTPException:
    return discord.HTTPException(MagicMock(status=stato, reason="errore"), "errore finto")


class Scena:
    """Un server finto con una categoria che crea vocali numerati da 2000."""

    def __init__(self) -> None:
        self.guild = fake_guild(ID_SERVER)
        self.guild.default_role = fake_role(role_id=ID_SERVER, name="@everyone", position=0)
        self.membri: dict[int, MagicMock] = {}
        self.guild.get_member.side_effect = self.membri.get
        self.canali: dict[int, MagicMock] = {}
        self.guild.get_channel.side_effect = self.canali.get
        self.categoria = create_autospec(discord.CategoryChannel, instance=True)
        self.categoria.id = 900
        self.categoria.channels = []
        self.categoria.create_voice_channel.side_effect = self._crea_canale

    async def _crea_canale(self, name, **kwargs):
        canale = fake_voice_channel(2000 + len(self.canali), name)
        canale.guild = self.guild
        self.canali[canale.id] = canale
        return canale

    def membro(self, user_id: int, *, bot: bool = False, manage_channels: bool = False):
        if user_id not in self.membri:
            membro = fake_member(
                user_id,
                bot=bot,
                guild_permissions=discord.Permissions(manage_channels=manage_channels),
            )
            membro.guild = self.guild
            membro.display_name = f"utente{user_id}"
            membro.voice = None
            self.membri[user_id] = membro
        return self.membri[user_id]

    def entra(self, membro, canale):
        membro.voice = create_autospec(discord.VoiceState, instance=True)
        membro.voice.channel = canale
        canale.members.append(membro)
        return membro

    async def crea_canale_di(self, proprietario):
        """Crea il vocale temporaneo come fa il bot e ci mette dentro il proprietario."""
        config = await voice_temp_repo.get_config(ID_SERVER)
        canale = await _create_temp_channel(self.guild, proprietario, self.categoria, config)
        self.entra(proprietario, canale)
        return canale

    def interazione(self, utente):
        return fake_interaction(guild=self.guild, user=utente)


def _testo(chiamata) -> str:
    return chiamata.args[0] if chiamata.args else chiamata.kwargs.get("content", "")


# ====================================================================
# M 7.1 — /voice rename: nome fino a 100 caratteri
# M 7.2 — terza rinomina in 10 minuti: messaggio, nessuna attesa
# ====================================================================
async def test_voice_rename_dichiara_da_1_a_100_caratteri():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await bot.add_cog(VoiceTempCog(bot))

    comando = bot.tree.get_command("voice").get_command("rename")
    opzioni = {o["name"]: o for o in comando.to_dict(bot.tree)["options"]}

    assert opzioni["name"]["min_length"] == 1
    assert opzioni["name"]["max_length"] == 100


async def _rinomina(scena, utente, nome: str):
    cog = VoiceTempCog(bot=None)
    interazione = scena.interazione(utente)
    await cog.rename.callback(cog, interazione, nome)
    return interazione


async def test_la_terza_rinomina_risponde_subito_riprova_tra():
    scena = Scena()
    proprietario = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(proprietario)

    for nome in ("Ranked", "Chill"):
        riuscita = await _rinomina(scena, proprietario, nome)
        riuscita.response.defer.assert_awaited_once()
        assert nome in _testo(riuscita.followup.send.call_args)
    terza = await _rinomina(scena, proprietario, "Terzo nome")

    assert [c.kwargs["name"] for c in canale.edit.call_args_list] == ["Ranked", "Chill"]
    risposta = terza.response.send_message.call_args
    assert "Riprova tra circa 10 minuti" in _testo(risposta)
    assert risposta.kwargs["ephemeral"] is True
    terza.response.defer.assert_not_awaited()


async def test_rinomina_rifiutata_da_discord_risposta_chiara():
    scena = Scena()
    proprietario = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(proprietario)
    canale.edit.side_effect = _errore_http(400)

    interazione = await _rinomina(scena, proprietario, "nome vietato")

    assert "Non sono riuscito a rinominare" in _testo(interazione.followup.send.call_args)
    # Un errore non consuma una delle due rinomine.
    assert rinomina.rename_tracker.seconds_until_allowed(canale.id) == 0


async def test_rinomina_con_discord_in_attesa_non_resta_appesa(monkeypatch):
    monkeypatch.setattr(rinomina, "RENAME_TIMEOUT_SECONDS", 0.05)
    scena = Scena()
    proprietario = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(proprietario)

    async def _attesa_infinita(**kwargs):
        await asyncio.sleep(600)

    canale.edit.side_effect = _attesa_infinita

    interazione = await asyncio.wait_for(_rinomina(scena, proprietario, "nuovo"), timeout=2)

    assert "Riprova tra circa 10 minuti" in _testo(interazione.followup.send.call_args)


async def test_il_nome_nella_conferma_non_puo_menzionare_nessuno():
    scena = Scena()
    proprietario = scena.membro(ID_PROPRIETARIO)
    await scena.crea_canale_di(proprietario)

    interazione = await _rinomina(scena, proprietario, "@everyone")

    menzioni = interazione.followup.send.call_args.kwargs["allowed_mentions"]
    assert menzioni.to_dict() == discord.AllowedMentions.none().to_dict()


@pytest.mark.parametrize("comando", ("limit", "lock", "unlock", "kick"))
async def test_gli_altri_comandi_di_gestione_gestiscono_l_errore_di_discord(comando):
    scena = Scena()
    proprietario = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(proprietario)
    ospite = scena.entra(scena.membro(ID_OSPITE), canale)
    canale.edit.side_effect = _errore_http(403)
    canale.set_permissions.side_effect = _errore_http(403)
    ospite.move_to.side_effect = _errore_http(403)
    cog = VoiceTempCog(bot=None)
    interazione = scena.interazione(proprietario)

    if comando == "limit":
        await cog.limit.callback(cog, interazione, 5)
    elif comando == "kick":
        await cog.kick.callback(cog, interazione, ospite)
    else:
        await getattr(cog, comando).callback(cog, interazione)

    risposta = interazione.response.send_message.call_args
    assert "Non sono riuscito" in _testo(risposta)
    assert risposta.kwargs["ephemeral"] is True


# ====================================================================
# M 7.4 — /voice transfer sposta i permessi del canale (BUG-18)
# ====================================================================
PERMESSI_DEL_PROPRIETARIO = ("manage_channels", "move_members", "mute_members")


async def _trasferisci(scena, chi, a_chi):
    cog = VoiceTempCog(bot=None)
    interazione = scena.interazione(chi)
    await cog.transfer.callback(cog, interazione, a_chi)
    return interazione


def _permessi_dati(canale) -> dict:
    """bersaglio -> PermissionOverwrite (o None se tolto) delle chiamate a set_permissions."""
    esito = {}
    for chiamata in canale.set_permissions.call_args_list:
        bersaglio = chiamata.args[0]
        if "overwrite" in chiamata.kwargs:
            esito[bersaglio.id] = chiamata.kwargs["overwrite"]
        else:
            permessi = {k: v for k, v in chiamata.kwargs.items() if k != "reason"}
            esito[bersaglio.id] = discord.PermissionOverwrite(**permessi)
    return esito


async def test_transfer_sposta_i_permessi_e_il_nuovo_proprietario_puo_rinominare():
    scena = Scena()
    vecchio = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(vecchio)
    nuovo = scena.entra(scena.membro(ID_OSPITE), canale)

    interazione = await _trasferisci(scena, vecchio, nuovo)

    assert await voice_temp_repo.get_owner(canale.id) == ID_OSPITE
    permessi = _permessi_dati(canale)
    for nome in PERMESSI_DEL_PROPRIETARIO:
        assert getattr(permessi[ID_OSPITE], nome) is True, nome
    assert permessi[ID_PROPRIETARIO] is None  # al vecchio proprietario vengono tolti
    assert nuovo.mention in _testo(interazione.response.send_message.call_args)

    # Il nuovo proprietario gestisce il canale, il vecchio non più.
    riuscita = await _rinomina(scena, nuovo, "Nuovo nome")
    assert canale.edit.call_args.kwargs["name"] == "Nuovo nome"
    assert "Nuovo nome" in _testo(riuscita.followup.send.call_args)
    rifiutata = await _rinomina(scena, vecchio, "Ci riprovo")
    assert "Solo il proprietario" in _testo(rifiutata.response.send_message.call_args)
    assert canale.edit.await_count == 1


async def test_transfer_fatto_dallo_staff_toglie_i_permessi_al_vero_proprietario():
    scena = Scena()
    vecchio = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(vecchio)
    nuovo = scena.entra(scena.membro(ID_OSPITE), canale)
    staff = scena.entra(scena.membro(30, manage_channels=True), canale)

    await _trasferisci(scena, staff, nuovo)

    permessi = _permessi_dati(canale)
    assert permessi[ID_PROPRIETARIO] is None
    assert 30 not in permessi
    assert await voice_temp_repo.get_owner(canale.id) == ID_OSPITE


async def test_transfer_permessi_rifiutati_da_discord_la_proprieta_non_cambia():
    scena = Scena()
    vecchio = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(vecchio)
    nuovo = scena.entra(scena.membro(ID_OSPITE), canale)
    canale.set_permissions.side_effect = _errore_http(403)

    interazione = await _trasferisci(scena, vecchio, nuovo)

    assert await voice_temp_repo.get_owner(canale.id) == ID_PROPRIETARIO
    risposta = interazione.response.send_message.call_args
    assert "Non sono riuscito" in _testo(risposta)
    assert risposta.kwargs["ephemeral"] is True


async def test_transfer_a_chi_e_gia_proprietario_non_fa_nulla():
    scena = Scena()
    proprietario = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(proprietario)

    interazione = await _trasferisci(scena, proprietario, proprietario)

    canale.set_permissions.assert_not_awaited()
    assert "già il proprietario" in _testo(interazione.response.send_message.call_args)


async def test_transfer_con_il_vecchio_proprietario_uscito_dal_server():
    scena = Scena()
    vecchio = scena.membro(ID_PROPRIETARIO)
    canale = await scena.crea_canale_di(vecchio)
    nuovo = scena.entra(scena.membro(ID_OSPITE), canale)
    staff = scena.entra(scena.membro(30, manage_channels=True), canale)
    del scena.membri[ID_PROPRIETARIO]  # non è più nel server

    await _trasferisci(scena, staff, nuovo)

    assert await voice_temp_repo.get_owner(canale.id) == ID_OSPITE
    assert list(_permessi_dati(canale)) == [ID_OSPITE]
