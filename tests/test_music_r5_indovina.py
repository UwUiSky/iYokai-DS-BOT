"""
tests/test_music_r5_indovina.py
===============================
Catalogo MUS (issue #126) giro r5mus: MUS-019, «indovina la canzone».
Logica pura (risposte, punti, tempi) e comando con un bot musicale finto.
"""

import pytest

from core import music_indovina_logic as il


def test_normalizza_senza_maiuscole_accenti_parentesi_e_punteggiatura():
    assert il.normalizza_risposta("  Città   VUOTA!! (Remix) [feat. X] ") == "citta vuota"
    assert il.normalizza_risposta("Beyoncé – Halo") == "beyonce halo"
    assert il.normalizza_risposta("") == "" and il.normalizza_risposta(None) == ""
    assert il.normalizza_risposta("？？？") == ""


def test_risposte_accettate_prende_titolo_e_parti():
    assert il.risposte_accettate("Artista - Titolo Bello") == {"artista titolo bello", "artista", "titolo bello"}
    assert il.risposte_accettate("Solo Titolo") == {"solo titolo"}
    assert il.risposte_accettate("") == frozenset()


@pytest.mark.parametrize("testo", [
    "citta vuota", "CITTÀ VUOTA", "Città vuota!!!", "è la canzone città vuota", "citta vuotta",
])
def test_risposte_giuste(testo):
    assert il.risposta_corretta(testo, il.risposte_accettate("Città Vuota (live)"))


@pytest.mark.parametrize("testo", [
    "", "   ", "citta", "vuota", "altra canzone", "x" * 300, "citta vuota " + "parola " * 100,
])
def test_risposte_sbagliate(testo):
    assert not il.risposta_corretta(testo, il.risposte_accettate("Città Vuota"))


def test_titoli_corti_solo_uguali():
    assert il.risposta_corretta("ok", il.risposte_accettate("Ok"))
    assert not il.risposta_corretta("va bene ok", il.risposte_accettate("Ok"))  # troppo corto per «contiene»
    assert not il.risposta_corretta("or", il.risposte_accettate("Ok"))


def test_inizio_estratto_dentro_il_brano():
    assert il.inizio_estratto_ms(10_000) == 0
    for durata in (60_000, 200_000, 3_600_000):
        for r in (0.0, 0.5, 0.999999):
            inizio = il.inizio_estratto_ms(durata, scelta=lambda r=r: r)
            assert il.INIZIO_MIN_MS <= inizio <= durata - il.ESTRATTO_SECONDI * 1000


def test_numero_di_round_con_tetti():
    assert il.numero_di_round(5, 20) == 5
    assert il.numero_di_round(50, 99) == il.MAX_ROUND
    assert il.numero_di_round(5, 3) == 3
    assert il.numero_di_round(0, 3) == 1
    assert il.numero_di_round(5, 0) == 0


def test_il_primo_che_indovina_vince_un_punto_e_chiude_il_giro():
    p = il.Partita(1, 2, 3, 2)
    p.apri_round("Titolo Uno")
    assert p.prova(10, "sbagliato") is False
    assert p.prova(11, "titolo uno") is True
    assert p.prova(12, "titolo uno") is False  # giro chiuso: nessun doppio punto
    assert p.punteggi == {11: 1}


def test_giro_chiuso_non_prende_risposte():
    p = il.Partita(1, 2, 3, 1)
    assert p.prova(10, "x") is False  # prima di aprire
    p.apri_round("Titolo")
    p.chiudi_round()
    assert p.prova(10, "titolo") is False and p.punteggi == {}


def test_tentativi_limitati_per_persona_e_per_giro():
    p = il.Partita(1, 2, 3, 1)
    p.apri_round("Titolo Lungo")
    for _ in range(il.MAX_TENTATIVI_PER_ROUND):
        assert p.prova(10, "boh") is False
    assert p.prova(10, "titolo lungo") is False  # troppi tentativi: anche quella giusta e' ignorata
    assert p.prova(11, "titolo lungo") is True


def test_i_punti_non_superano_i_giri_e_non_si_accumulano_senza_fine():
    p = il.Partita(1, 2, 3, 3)
    for n in range(10):
        if p.ultimo_round():
            break
        p.apri_round(f"Brano {n}")
        assert p.prova(10, f"brano {n}")
    assert p.punteggi[10] == 3 and p.round_corrente == 3 and p.ultimo_round()


def test_classifica_ordinata_e_con_tetto():
    p = il.Partita(1, 2, 3, 10)
    p.punteggi = {5: 2, 6: 3, 7: 2}
    assert p.classifica() == [(6, 3), (5, 2), (7, 2)]
    assert len(il.Partita(1, 2, 3, 1, punteggi={i: 1 for i in range(50)}).classifica()) == 10


# ----------------------------- comando e partita -----------------------------
import asyncio  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from unittest.mock import AsyncMock  # noqa: E402

import cogs.music.indovina as modulo  # noqa: E402


def _brano(i):
    return SimpleNamespace(identifier=f"https://x.example.com/{i}", label=f"Titolo {i}", duration_ms=200_000)


class _Mondo:
    """Un bot musicale finto: tiene il player e conta cosa succede."""

    def __init__(self, sessione_presente=False):
        self.player = SimpleNamespace(
            current=SimpleNamespace(length=200_000, is_seekable=True),
            seek=AsyncMock(), skip=AsyncMock(), disconnect=AsyncMock(),
        )
        self.accodati = []
        self.rilasci = []
        self.attiva = sessione_presente
        guild_worker = SimpleNamespace(voice_client=self.player)
        self.fleet = SimpleNamespace(
            get_worker_for_channel=AsyncMock(side_effect=lambda g, c: (1, SimpleNamespace(get_guild=lambda gid: guild_worker)) if self.attiva else None),
            release_session=AsyncMock(side_effect=lambda g, c: self.rilasci.append((g, c))),
        )

        async def accoda(guild, membro, query, rispondi, **kw):
            self.accodati.append((query, kw.get("gratis")))
            self.attiva = True
            return 11

        self.musica = SimpleNamespace(
            _controlli_base=AsyncMock(return_value=True), accoda=accoda, _cerca_su=AsyncMock(),
        )


def _cog(mondo):
    bot = SimpleNamespace(get_cog=lambda n: mondo.musica, music_fleet=mondo.fleet)
    return modulo.MusicIndovinaCog(bot)


def _interazione(user_id=5):
    inviati = []

    async def invia(testo=None, **kw):
        inviati.append(testo)

    canale = SimpleNamespace(
        id=77, send=AsyncMock(side_effect=lambda testo, **kw: inviati.append(testo)),
        permissions_for=lambda m: SimpleNamespace(send_messages=True, view_channel=True),
    )
    user = SimpleNamespace(id=user_id, voice=SimpleNamespace(channel=SimpleNamespace(id=11)),
                           guild_permissions=SimpleNamespace(manage_guild=False))
    guild = SimpleNamespace(id=900, me=object())
    user.guild = guild
    return SimpleNamespace(
        guild=guild, user=user, channel=canale, channel_id=77, inviati=inviati,
        response=SimpleNamespace(send_message=AsyncMock(side_effect=invia)),
    )


@pytest.fixture(autouse=True)
def _tempi_brevi(monkeypatch):
    for nome, valore in (("ESTRATTO_SECONDI", 0.05), ("TEMPO_ROUND_SECONDI", 0.1), ("PAUSA_TRA_ROUND_SECONDI", 0.01)):
        monkeypatch.setattr(modulo, nome, valore)
    from core import music_indovina_logic as il2
    yield
    for g in list(il2._in_gioco):
        il2.togli_in_gioco(g)


def _con_brani(monkeypatch, n=3, locali=0):
    brani = [_brano(i) for i in range(n)] + [
        SimpleNamespace(identifier=f"local:/musica/{i}.mp3", label=f"Inedito {i}", duration_ms=1000) for i in range(locali)
    ]
    monkeypatch.setattr(modulo.main_radio_repo, "list_tracks", AsyncMock(return_value=brani), raising=False)
    monkeypatch.setattr(modulo, "lingua_risposta", AsyncMock(return_value="it"))
    monkeypatch.setattr(modulo, "testo_per", AsyncMock(side_effect=lambda i, k, **kw: k))


async def _finisci(cog):
    for c in list(cog._partite.values()):
        await asyncio.gather(c.task, return_exceptions=True)
    await asyncio.sleep(0.02)  # la pulizia parte a compito finito
    await asyncio.gather(*cog._pulizie)


async def test_partita_completa_nessuno_risponde(monkeypatch):
    _con_brani(monkeypatch, 3, locali=2)
    mondo = _Mondo()
    cog = _cog(mondo)
    inter = _interazione()
    await cog.indovina.callback(cog, inter, 2, False)
    assert modulo.in_gioco(900)
    await _finisci(cog)
    assert len(mondo.accodati) == 2
    assert all(q.startswith("https://") and gratis is True for q, gratis in mondo.accodati)  # niente locali, mai a pagamento
    assert any("Tempo scaduto" in m or "scaduto" in m for m in inter.inviati if m)
    assert mondo.player.disconnect.await_count == 1 and mondo.rilasci == [(900, 11)]
    assert not modulo.in_gioco(900) and 900 not in cog._partite


async def test_il_primo_che_indovina_prende_il_punto_e_il_titolo_resta_segreto_prima(monkeypatch):
    _con_brani(monkeypatch, 1)
    mondo = _Mondo()
    cog = _cog(mondo)
    inter = _interazione()
    await cog.indovina.callback(cog, inter, 1, False)
    messaggio = lambda testo, uid=42: SimpleNamespace(
        author=SimpleNamespace(id=uid, bot=False), guild=inter.guild, channel=SimpleNamespace(id=77), content=testo
    )
    await asyncio.sleep(0.01)
    await cog.on_message(SimpleNamespace(author=SimpleNamespace(id=1, bot=True), guild=inter.guild, channel=SimpleNamespace(id=77), content="titolo 0"))  # un bot
    await cog.on_message(SimpleNamespace(author=SimpleNamespace(id=2, bot=False), guild=inter.guild, channel=SimpleNamespace(id=88), content="titolo 0"))  # altro canale
    assert cog._partite[900].partita.punteggi == {}
    await cog.on_message(messaggio("titolo 0"))
    await _finisci(cog)
    testi = [m for m in inter.inviati if m]
    assert any("<@42>" in m and "Titolo 0" in m for m in testi)
    assert not any("Titolo 0" in m for m in testi[:2])  # inizio e giro non rivelano il titolo


async def test_non_parte_senza_brani_con_musica_in_corso_o_con_una_partita_gia_aperta(monkeypatch):
    _con_brani(monkeypatch, 0, locali=2)
    cog = _cog(_Mondo())
    inter = _interazione()
    await cog.indovina.callback(cog, inter, 3, False)
    assert inter.inviati == ["indovina_nessun_brano"] and 900 not in cog._partite
    _con_brani(monkeypatch, 3)
    cog2 = _cog(_Mondo(sessione_presente=True))
    inter2 = _interazione()
    await cog2.indovina.callback(cog2, inter2, 3, False)
    assert inter2.inviati == ["indovina_musica_in_corso"]
    cog3 = _cog(_Mondo())
    await cog3.indovina.callback(cog3, _interazione(), 3, False)
    doppia = _interazione()
    await cog3.indovina.callback(cog3, doppia, 3, False)
    assert doppia.inviati == ["indovina_gia_in_corso"]
    await _finisci(cog3)


async def test_dopo_una_partita_serve_una_pausa(monkeypatch):
    _con_brani(monkeypatch, 1)
    cog = _cog(_Mondo())
    await cog.indovina.callback(cog, _interazione(), 1, False)
    await _finisci(cog)
    ancora = _interazione()
    await cog.indovina.callback(cog, ancora, 1, False)
    assert ancora.inviati == ["indovina_attendi"]


async def test_ferma_solo_chi_ha_avviato_o_chi_gestisce(monkeypatch):
    _con_brani(monkeypatch, 3)
    mondo = _Mondo()
    cog = _cog(mondo)
    monkeypatch.setattr(modulo, "TEMPO_ROUND_SECONDI", 5)
    monkeypatch.setattr(modulo, "ESTRATTO_SECONDI", 5)
    await cog.indovina.callback(cog, _interazione(5), 3, False)
    estraneo = _interazione(9)
    await cog.indovina.callback(cog, estraneo, 3, True)
    assert estraneo.inviati == ["indovina_solo_chi_ha_avviato"] and 900 in cog._partite
    await cog.indovina.callback(cog, _interazione(5), 3, True)
    await _finisci(cog)
    assert 900 not in cog._partite and not modulo.in_gioco(900)
    assert mondo.rilasci == [(900, 11)]  # fermata prima del primo brano: nessun player, ma lo slot si libera


async def test_se_il_bot_non_riesce_a_suonare_la_partita_finisce_e_pulisce(monkeypatch):
    _con_brani(monkeypatch, 2)
    mondo = _Mondo()

    async def fallisce(*a, **k):
        return None

    mondo.musica.accoda = fallisce
    cog = _cog(mondo)
    inter = _interazione()
    await cog.indovina.callback(cog, inter, 2, False)
    await _finisci(cog)
    assert "indovina_interrotta" not in inter.inviati  # il testo e' tradotto, non la chiave
    assert not modulo.in_gioco(900) and 900 not in cog._partite


async def test_durante_la_partita_annunci_e_riserva_non_rivelano_niente(monkeypatch):
    import cogs.music.eventi as eventi

    segna = modulo.segna_in_gioco
    segna(900)
    canale = SimpleNamespace(send=AsyncMock())
    cog = eventi.MusicEventiCog(SimpleNamespace(get_channel=lambda i: canale))
    cog.riserva = AsyncMock()
    player = SimpleNamespace(guild=SimpleNamespace(id=900), is_radio=False, is_nonstop=False,
                             queue=SimpleNamespace(is_empty=True), current=None)
    caricate = AsyncMock()
    monkeypatch.setattr(eventi, "load_music_settings", caricate)
    await cog.su_inizio_brano(SimpleNamespace(player=player, track=SimpleNamespace(title="Segreto")))
    await cog.su_fine_brano(SimpleNamespace(player=player, reason="finished"))
    caricate.assert_not_awaited()  # nessuna lettura di impostazioni: uscita subito
    cog.riserva.assert_not_called()
    canale.send.assert_not_awaited()
