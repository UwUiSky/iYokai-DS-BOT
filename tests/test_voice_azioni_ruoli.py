"""
tests/test_voice_azioni_ruoli.py
================================
Azioni del proprietario di un vocale temporaneo, per ruolo (VOC-017): logica, impostazione salvata e blocco nel comando.
Funzioni coperte: VOC-017
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core import voice_azioni_ruoli as va


# VOC-017
def test_un_ruolo_vietato_non_puo_fare_quell_azione_e_gli_altri_si():
    vietate = {"kick": [10], "rename": [10, 11]}
    assert va.azione_permessa(vietate, "kick", {10, 5}) is False
    assert va.azione_permessa(vietate, "kick", {5}) is True
    assert va.azione_permessa(vietate, "lock", {10}) is True  # solo le azioni scelte
    assert va.azione_permessa({}, "kick", {10}) is True


# VOC-017
def test_la_mappa_si_cambia_senza_toccare_l_originale_e_ha_un_tetto():
    base = {"kick": [10]}
    nuova = va.con_modifica(base, "kick", 11, consenti=False)
    assert nuova == {"kick": [10, 11]} and base == {"kick": [10]}
    assert va.con_modifica(nuova, "kick", 10, consenti=True) == {"kick": [11]}
    assert va.con_modifica({"kick": [10]}, "kick", 10, consenti=True) == {}
    pieno = {"kick": list(range(1, 11))}
    with pytest.raises(va.AzioneNonValida):
        va.con_modifica(pieno, "kick", 99, consenti=False)
    with pytest.raises(va.AzioneNonValida):
        va.con_modifica({}, "inventata", 1, consenti=False)


# VOC-017
def test_un_valore_salvato_strano_non_rompe_niente():
    assert va.pulisci("x") == {} and va.pulisci(None) == {}
    assert va.pulisci({"kick": [1, "2", True, -3, 1], "inventata": [5], "lock": "no"}) == {"kick": [1]}


# VOC-017
@pytest.mark.asyncio
async def test_l_impostazione_si_salva_e_si_toglie(clean_db, monkeypatch):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._settings_cache.clear()
    await database_module.db.ensure_guild_exists(930)
    assert await va.leggi(930) == {}
    assert await va.imposta(930, "kick", 77, False, 1) == {"kick": [77]}
    assert await va.leggi(930) == {"kick": [77]}
    assert await va.imposta(930, "kick", 77, True, 1) == {}
    assert await va.leggi(930) == {}


# VOC-017
@pytest.mark.asyncio
async def test_il_comando_del_proprietario_e_rifiutato_per_un_ruolo_vietato(monkeypatch):
    import cogs.voice_temp.voice_temp as modulo

    canale = MagicMock(id=5)
    utente = MagicMock(spec=modulo.discord.Member)
    utente.id = 1
    utente.voice = MagicMock(channel=canale)
    utente.roles = [MagicMock(id=10)]
    utente.guild_permissions = modulo.discord.Permissions.none()
    interazione = MagicMock()
    interazione.user = utente
    interazione.guild = MagicMock(id=930)
    interazione.response = MagicMock(send_message=AsyncMock())
    monkeypatch.setattr(modulo.voice_temp_repo, "get_owner", AsyncMock(return_value=1))
    monkeypatch.setattr(modulo.azioni_ruoli, "leggi", AsyncMock(return_value={"kick": [10]}))
    cog = modulo.VoiceTempCog.__new__(modulo.VoiceTempCog)
    assert await cog._get_managed_channel_or_reply(interazione, "kick") is None
    interazione.response.send_message.assert_awaited_once()
    interazione.response.send_message.reset_mock()
    assert await cog._get_managed_channel_or_reply(interazione, "lock") is canale  # altra azione: permessa
    # chi gestisce i canali (staff) non è mai fermato
    utente.guild_permissions = modulo.discord.Permissions(manage_channels=True)
    assert await cog._get_managed_channel_or_reply(interazione, "kick") is canale
