"""
tests/test_suono_ferma.py
=========================
FUN-078 (#131, D111) # FUN-078: fermare il suono in corso. Lo ferma chi l'ha fatto partire; se non è più nel canale
(nessuno controlla il suono) chiunque sia nel canale; staff e DJ sempre; chi sta fuori dal canale no.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import cogs.fun.soundboard as modulo
from core.music_sound_logic import SuoniInCorso, puo_fermare_suono
from tests.test_soundboard_play import _cog, _interazione, _Musica, _WorkerGuild, _CanaleVoce, _nulla

pytestmark = pytest.mark.asyncio


# ---- regole pure ----
def test_chi_l_ha_avviato_lo_ferma_anche_se_e_uscito():
    assert puo_fermare_suono(False, avviato_da=9, utente_id=9, ascoltatori_umani={9, 5})
    assert puo_fermare_suono(False, avviato_da=9, utente_id=9, ascoltatori_umani={5})


def test_un_altro_nel_canale_solo_se_chi_l_ha_avviato_non_c_e_piu():
    assert not puo_fermare_suono(False, avviato_da=9, utente_id=5, ascoltatori_umani={9, 5})
    assert puo_fermare_suono(False, avviato_da=9, utente_id=5, ascoltatori_umani={5, 6})


def test_chi_sta_fuori_dal_canale_non_lo_ferma():
    assert not puo_fermare_suono(False, avviato_da=9, utente_id=5, ascoltatori_umani={9})
    assert not puo_fermare_suono(False, avviato_da=9, utente_id=5, ascoltatori_umani=set())


def test_staff_e_dj_sempre():
    assert puo_fermare_suono(True, avviato_da=9, utente_id=5, ascoltatori_umani={9, 5})
    assert puo_fermare_suono(True, avviato_da=9, utente_id=5, ascoltatori_umani=set())


def test_il_suono_dura_pochi_secondi():
    adesso = [0.0]
    suoni = SuoniInCorso(durata=8, orologio=lambda: adesso[0])
    suoni.segna(1, 3, 9, True)
    adesso[0] = 7.9
    assert suoni.attivo(1, 3).avviato_da == 9
    adesso[0] = 8.1
    assert suoni.attivo(1, 3) is None
    assert suoni.attivo(1, 4) is None


# ---- comando ----
class _MusicaVoce(_Musica):
    def __init__(self, worker_guild, umani, privilegiato=False):
        super().__init__(worker_guild)
        self.umani = umani
        self.privilegiato = privilegiato
        self.disconnessioni = 0

    def _ascoltatori_umani(self, canale):
        return list(self.umani)

    async def _privilegi(self, interazione, impostazioni=None):
        return self.privilegiato

    async def _entra_in_canale(self, canale, nodo, volume=None, sordo=True):
        self.ingressi.append(sordo)

        async def _disconnetti():
            self.disconnessioni += 1
            self.worker_guild.voice_client = None

        player = SimpleNamespace(
            channel=canale, playing=False, queue=SimpleNamespace(is_empty=True), disconnect=_disconnetti
        )
        self.worker_guild.voice_client = player
        return player, None


def _chi(user_id, canale_id=3):
    return SimpleNamespace(id=user_id, voice=SimpleNamespace(channel=SimpleNamespace(id=canale_id)))


async def _suono_partito(monkeypatch, umani, privilegiato=False, musica_in_riproduzione=False):
    worker_guild = _WorkerGuild(player=SimpleNamespace(channel=_CanaleVoce(), playing=True) if musica_in_riproduzione else None)
    musica = _MusicaVoce(worker_guild, umani, privilegiato)
    cog, _, predefinito = _cog(musica, monkeypatch)

    async def _esci(*a, **kw):
        return None

    monkeypatch.setattr(modulo, "_esci_se_inattivo", _esci)
    interazione, testi = _interazione([])
    interazione.guild.get_channel = lambda cid: SimpleNamespace(id=cid)
    await cog.suono.callback(cog, interazione, nome="Grillo")  # lo avvia l'utente 9
    return cog, musica, interazione, testi


def _stessa_guild(interazione, user):
    return SimpleNamespace(guild=interazione.guild, user=user)


async def test_chi_l_ha_avviato_lo_ferma_e_il_bot_esce(monkeypatch):
    cog, musica, i, testi = await _suono_partito(monkeypatch, umani={9, 5})
    assert (await cog.ferma_suono(_stessa_guild(i, _chi(9)), 3)) == "suono_fermato"
    assert musica.disconnessioni == 1
    assert (await cog.ferma_suono(_stessa_guild(i, _chi(9)), 3)) == "suono_nessuno_in_corso"  # già fermo


async def test_un_altro_nel_canale_non_lo_ferma_se_chi_l_ha_avviato_c_e(monkeypatch):
    cog, musica, i, _ = await _suono_partito(monkeypatch, umani={9, 5})
    assert (await cog.ferma_suono(_stessa_guild(i, _chi(5)), 3)) == "suono_non_tuo"
    assert musica.disconnessioni == 0


async def test_se_chi_l_ha_avviato_e_uscito_lo_ferma_chiunque_nel_canale(monkeypatch):
    cog, musica, i, _ = await _suono_partito(monkeypatch, umani={5, 6})
    assert (await cog.ferma_suono(_stessa_guild(i, _chi(5)), 3)) == "suono_fermato"
    assert musica.disconnessioni == 1


async def test_chi_sta_in_un_altro_canale_non_lo_ferma_nemmeno_lo_staff(monkeypatch):
    cog, musica, i, _ = await _suono_partito(monkeypatch, umani={9, 5}, privilegiato=True)
    assert (await cog.ferma_suono(_stessa_guild(i, _chi(5, canale_id=77)), 3)) == "suono_altro_canale"
    assert musica.disconnessioni == 0


async def test_staff_e_dj_lo_fermano_sempre(monkeypatch):
    cog, musica, i, _ = await _suono_partito(monkeypatch, umani={9, 5}, privilegiato=True)
    assert (await cog.ferma_suono(_stessa_guild(i, _chi(5)), 3)) == "suono_fermato"


async def test_con_la_musica_in_riproduzione_non_si_esce(monkeypatch):
    cog, musica, i, _ = await _suono_partito(monkeypatch, umani={9}, musica_in_riproduzione=True)
    assert (await cog.ferma_suono(_stessa_guild(i, _chi(9)), 3)) == "suono_con_musica"
    assert musica.disconnessioni == 0 and worker_voice_ancora_li(musica)


def worker_voice_ancora_li(musica):
    return musica.worker_guild.voice_client is not None


async def test_dopo_la_durata_il_suono_non_e_piu_in_corso(monkeypatch):
    cog, musica, i, _ = await _suono_partito(monkeypatch, umani={9})
    cog._in_corso._orologio = lambda: 10**9
    assert (await cog.ferma_suono(_stessa_guild(i, _chi(9)), 3)) == "suono_nessuno_in_corso"


async def test_il_bottone_sotto_il_suono_usa_gli_stessi_controlli(monkeypatch):
    cog, musica, i, testi = await _suono_partito(monkeypatch, umani={9, 5})
    vista = modulo.FermaSuonoView(cog, 3)
    risposte = []

    async def _rispondi(testo=None, **kw):
        risposte.append(testo)

    estraneo = SimpleNamespace(
        guild=i.guild, user=_chi(5), response=SimpleNamespace(send_message=_rispondi)
    )
    await vista.ferma.callback(estraneo)
    assert "Lo ferma chi l'ha fatto partire" in risposte[-1] and musica.disconnessioni == 0
    avviatore = SimpleNamespace(guild=i.guild, user=_chi(9), response=SimpleNamespace(send_message=_rispondi))
    await vista.ferma.callback(avviatore)
    assert musica.disconnessioni == 1
