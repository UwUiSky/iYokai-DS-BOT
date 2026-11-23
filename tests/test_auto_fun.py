"""
tests/test_auto_fun.py
======================
Auto da collezione (FUN-017, #131): regole, garage, acquisti e potenziamenti atomici, gara con puntata, foto
ricodificata (D74), segnalazioni e rimozione da parte dello staff.
Funzioni coperte: FUN-017
"""

import asyncio
import io
import random
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image

from cogs.fun import auto as cog_auto
from cogs.fun.auto import AutoCog, GaraView, SegnalaFotoView
from core import auto_logic as al
from core.auto_image import affianca, riduci_foto
from core.repositories.auto_repo import AutoRepository, Esito
from core.repositories.immagini_segnalazioni_repo import ImmaginiSegnalazioniRepository
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.partite_repo import PartiteRepository
from tests.support.concorrenza import apri_connessioni
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

G = 100


class RngFisso(random.Random):
    def __init__(self, tiri=()):
        super().__init__(1)
        self.tiri = list(tiri)

    def randint(self, a, b):
        return self.tiri.pop(0) if self.tiri else a

    def choice(self, seq):
        return seq[0]


def png(colore=(200, 30, 30), dim=(40, 20)) -> bytes:
    f = io.BytesIO()
    Image.new("RGB", dim, colore).save(f, format="PNG")
    return f.getvalue()


# ---------------------------------------------------------------- regole pure
def test_catalogo_coerente():
    assert len({m.chiave for m in al.CATALOGO}) == al.MAX_AUTO and all(m.rarita in al.RARITA for m in al.CATALOGO)
    assert al.trova("kitsune").nome == "Kitsune GT" and al.trova("nonesiste") is None
    assert cog_auto.risolvi("  Kitsune GT ").chiave == "kitsune" and cog_auto.risolvi("zzz") is None


def test_potenziamenti_e_costi():
    m = al.trova("risaia")
    assert al.statistiche(m, 0, 0, 0) == (38, 40, 42)
    assert al.statistiche(m, 2, 1, 3) == (38 + 8, 40 + 12, 42 + 4)  # motore -> velocità, gomme -> accelerazione, assetto -> tenuta
    assert [al.costo_potenziamento(1, n) for n in range(5)] == [60, 120, 180, 240, 300]
    with pytest.raises(ValueError):
        al.costo_potenziamento(1, al.LIVELLO_MASSIMO)


def test_gara_a_prove_e_vincitore():
    e = al.gara((90, 90, 90), (10, 10, 10), RngFisso())
    assert e.vincitore == 1 and [p[3] for p in e.prove] == [1, 1, 1]
    e = al.gara((10, 10, 10), (90, 90, 90), RngFisso())
    assert e.vincitore == 2
    e = al.gara((50, 50, 50), (50, 50, 50), RngFisso())  # tutto pari: decide il caso, mai uno stallo
    assert e.vincitore in (1, 2)
    for _ in range(50):
        assert al.gara((60, 60, 60), (50, 50, 50)).vincitore in (1, 2)


def test_avversario_del_banco_ha_la_stessa_rarita():
    for r in al.RARITA:
        m, a, b, c = al.avversario_del_banco(r, RngFisso())
        assert m.rarita == r and 0 <= a <= 3 and 0 <= b <= 3 and 0 <= c <= 3


# ---------------------------------------------------------------- immagini
def test_riduci_foto_rifa_il_png_senza_metadati_e_affianca():
    grande = png(dim=(2000, 1000))
    piccola = riduci_foto(grande)
    img = Image.open(io.BytesIO(piccola))
    assert img.format == "PNG" and max(img.size) <= al.LATO_FOTO and not img.info.get("exif")
    with pytest.raises(Exception):
        riduci_foto(b"non e' un png")
    tela = Image.open(io.BytesIO(affianca(piccola, None, 1)))
    assert tela.format == "PNG" and tela.width > tela.height
    assert Image.open(io.BytesIO(affianca(None, None, 0))).format == "PNG"


# ---------------------------------------------------------------- database
@pytest.fixture
def r(clean_db, monkeypatch):
    import core.ui_base as ui
    from core.repositories.leveling_settings_repo import LevelingSettingsRepository
    from core.repositories.sociale_repo import SocialeRepository

    async def nessuno(*a, **k):
        return False

    async def attivo(*a, **k):
        return True

    monkeypatch.setattr(ui, "_utente_o_server_in_blacklist", nessuno)
    ripo = AutoRepository(pool_provider=lambda: clean_db)
    partite = PartiteRepository(pool_provider=lambda: clean_db)
    segn = ImmaginiSegnalazioniRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(cog_auto, "auto_repo", ripo)
    monkeypatch.setattr(cog_auto, "partite_repo", partite)
    monkeypatch.setattr(cog_auto, "immagini_segnalazioni_repo", segn)
    monkeypatch.setattr(cog_auto, "sociale_repo", SocialeRepository(pool_provider=lambda: clean_db))
    monkeypatch.setattr(cog_auto, "leveling_settings_repo", LevelingSettingsRepository(pool_provider=lambda: clean_db))
    monkeypatch.setattr(cog_auto.db, "is_module_active_for_guild", attivo)
    return SimpleNamespace(a=ripo, p=partite, s=segn, lev=LevelingRepository(pool_provider=lambda: clean_db), pool=clean_db)


def _i(membro):
    i = fake_interaction(guild=fake_guild(G), user=membro)
    i.response.edit_message = AsyncMock()
    i.edit_original_response = AsyncMock()
    return i


async def _saldo(r, u):
    return (await r.lev.get_totals(G, u)).coins_total


@pytest.mark.asyncio
async def test_compra_atomica_senza_monete_o_due_volte(r):
    assert await r.a.compra(G, 1, "risaia") is Esito.POCHE  # nessuna riga di saldo
    assert await r.a.garage(G, 1) == []  # e niente auto: l'acquisto è annullato intero
    await r.lev.add_coins(G, 1, 400)
    assert await r.a.compra(G, 1, "risaia") is Esito.OK and await _saldo(r, 1) == 250
    assert await r.a.compra(G, 1, "risaia") is Esito.GIA and await _saldo(r, 1) == 250
    assert [a.modello for a in await r.a.garage(G, 1)] == ["risaia"]
    assert await r.a.compra(G, 1, "yokai") is Esito.POCHE and await _saldo(r, 1) == 250
    with pytest.raises(ValueError):
        await r.a.compra(G, 1, "nonesiste")


@pytest.mark.asyncio
async def test_due_acquisti_insieme_pagano_una_volta(r):
    await r.lev.add_coins(G, 1, 1000)
    await apri_connessioni(r.pool, 4)
    esiti = await asyncio.gather(*(r.a.compra(G, 1, "risaia") for _ in range(4)))
    assert sorted(e.value for e in esiti) == ["gia", "gia", "gia", "ok"] and await _saldo(r, 1) == 850


@pytest.mark.asyncio
async def test_potenziamento_costo_livello_massimo_e_concorrenza(r):
    await r.lev.add_coins(G, 1, 150 + 60)  # l'auto più il primo livello: il secondo (120) non c'è
    await r.a.compra(G, 1, "risaia")
    assert await r.a.potenzia(G, 1, "risaia", "motore") == (Esito.OK, 1, 60) and await _saldo(r, 1) == 0
    assert (await r.a.potenzia(G, 1, "risaia", "motore"))[0] is Esito.POCHE
    assert (await r.a.auto(G, 1, "risaia")).motore == 1
    assert (await r.a.potenzia(G, 1, "kitsune", "gomme"))[0] is Esito.MANCA
    with pytest.raises(ValueError):
        await r.a.potenzia(G, 1, "risaia", "freni; DROP TABLE x")
    await r.lev.add_coins(G, 1, 60)  # due potenziamenti insieme con i soldi per uno solo di quelli da 60
    await apri_connessioni(r.pool, 3)
    esiti = await asyncio.gather(r.a.potenzia(G, 1, "risaia", "assetto"), r.a.potenzia(G, 1, "risaia", "assetto"))
    assert sorted(e[0].value for e in esiti) == ["ok", "poche"] and await _saldo(r, 1) == 0
    assert (await r.a.auto(G, 1, "risaia")).assetto == 1
    await r.pool.execute("UPDATE fun_auto_garage SET gomme = 5")
    assert (await r.a.potenzia(G, 1, "risaia", "gomme"))[0] is Esito.MASSIMO


@pytest.mark.asyncio
async def test_foto_si_salva_si_sostituisce_si_toglie_e_segue_l_auto(r):
    await r.lev.add_coins(G, 1, 500)
    await r.a.compra(G, 1, "risaia")
    assert not await r.a.imposta_foto(G, 1, "kitsune", png(), "a" * 64)  # non è nel garage
    assert await r.a.imposta_foto(G, 1, "risaia", png(), "a" * 64)
    assert await r.a.imposta_foto(G, 1, "risaia", png((1, 2, 3)), "b" * 64)  # sostituisce
    assert (await r.a.foto(G, 1, "risaia"))[1] == "b" * 64
    assert (await r.a.auto(G, 1, "risaia")).con_foto
    with pytest.raises(ValueError):
        await r.a.imposta_foto(G, 1, "risaia", b"x" * (3 * 1024 * 1024), "c" * 64)
    assert await r.a.togli_foto(G, 1, "risaia") == 1 and await r.a.foto(G, 1, "risaia") is None
    await r.a.imposta_foto(G, 1, "risaia", png(), "a" * 64)
    assert await r.a.togli_foto(G, 1) == 1  # tutte quelle dell'utente (staff)
    await r.a.imposta_foto(G, 1, "risaia", png(), "a" * 64)
    await r.pool.execute("DELETE FROM fun_auto_garage")  # se l'auto sparisce sparisce anche la foto
    assert await r.pool.fetchval("SELECT count(*) FROM fun_auto_foto") == 0


@pytest.mark.asyncio
async def test_gara_con_puntata_paga_il_doppio_una_volta_e_conta_le_statistiche(r, monkeypatch):
    for u in (1, 2):
        await r.lev.add_coins(G, u, 1000)
        await r.a.compra(G, u, "risaia")
    a, b = fake_member(1), fake_member(2)
    mia = await r.a.auto(G, 1, "risaia")
    monkeypatch.setattr(cog_auto.al, "gara", lambda x, y, rng=None: al.Esito(1, (("rettilineo", 50, 40, 1), ("partenza", 50, 40, 1), ("curve", 50, 40, 1))))
    v = GaraView(AutoCog(MagicMock()), G, a, b, mia, 100, "coin")
    v.cog._rimborsi.cancel()
    await v._accetta(_i(a))  # lo sfidante non accetta
    assert v.fase == "attesa"
    i = _i(b)
    await v._accetta(i)
    assert await _saldo(r, 1) == 950 and await _saldo(r, 2) == 750 and v.fase == "fine"
    i.edit_original_response.assert_awaited()
    await v._accetta(_i(b))  # secondo clic: niente di nuovo
    assert await _saldo(r, 1) == 950 and await _saldo(r, 2) == 750
    assert [(x.corse, x.vinte) for x in (await r.a.garage(G, 1) + await r.a.garage(G, 2))] == [(1, 1), (1, 0)]
    assert await r.pool.fetchval("SELECT count(*) FROM economia_partite_aperte") == 0


@pytest.mark.asyncio
async def test_gara_senza_soldi_per_uno_non_toglie_niente_a_nessuno(r):
    await r.lev.add_coins(G, 1, 1000)
    await r.lev.add_coins(G, 2, 200)  # 150 per l'auto: ne restano 50
    await r.a.compra(G, 1, "risaia")
    await r.a.compra(G, 2, "risaia")
    v = GaraView(AutoCog(MagicMock()), G, fake_member(1), fake_member(2), await r.a.auto(G, 1, "risaia"), 100, "coin")
    v.cog._rimborsi.cancel()
    await v._accetta(_i(fake_member(2)))
    assert await _saldo(r, 1) == 850 and await _saldo(r, 2) == 50
    assert await r.pool.fetchval("SELECT count(*) FROM economia_partite_aperte") == 0
    assert [x.corse for x in await r.a.garage(G, 1)] == [0]


@pytest.mark.asyncio
async def test_segnalazioni_nascondono_la_foto_dopo_tre_persone(r):
    await r.lev.add_coins(G, 1, 500)
    await r.a.compra(G, 1, "risaia")
    await r.a.imposta_foto(G, 1, "risaia", png(), "d" * 64)
    auto = await r.a.auto(G, 1, "risaia")
    assert await cog_auto.foto_visibile(G, auto) is not None
    chiave = cog_auto.chiave_foto(G, 1, auto.sha_foto)
    for u in (7, 8, 9):
        await r.s.segnala(chiave, u, G)
    assert await cog_auto.foto_visibile(G, auto) is None  # nascosta, ma l'utente può ancora toglierla
    await r.a.imposta_foto(G, 1, "risaia", png((9, 9, 9)), "e" * 64)  # un'altra foto: un'altra chiave
    assert await cog_auto.foto_visibile(G, await r.a.auto(G, 1, "risaia")) is not None


@pytest.mark.asyncio
async def test_il_bottone_segnala_nasconde_al_terzo(r):
    v = SegnalaFotoView([("auto:1:2:abc", "Risaia 600")], "Segnala")
    for n, u in enumerate((7, 8, 9)):
        i = _i(fake_member(u))
        await v.children[0].callback(i)
        if n < 2:
            assert i.response.send_message.await_args.kwargs["ephemeral"] is True
        else:
            assert i.response.edit_message.await_args.kwargs["attachments"] == []


def _allegato(dati: bytes, nome="foto.png", ctype="image/png", dimensione=None):
    a = MagicMock()
    a.size = dimensione if dimensione is not None else len(dati)
    a.filename, a.content_type = nome, ctype
    a.read = AsyncMock(return_value=dati)
    return a


@pytest.mark.asyncio
async def test_il_comando_foto_salva_solo_la_copia_ricodificata(r, monkeypatch):
    await r.lev.add_coins(G, 1, 500)
    await r.a.compra(G, 1, "risaia")
    visti = {}

    async def finto_esamina(dati, nome, ctype, guild_id, **k):
        from core import allegati_tipo_logic as t

        visti["originale"] = dati
        return ("foto.png", png((5, 5, 5), (3000, 2000))), t.decidi(dati, nome, ctype)

    monkeypatch.setattr(cog_auto, "esamina_allegato", finto_esamina)
    cog = AutoCog(MagicMock())
    cog._rimborsi.cancel()
    originale = png()
    i = _i(fake_member(1))
    await AutoCog.foto.callback(cog, i, "risaia", _allegato(originale))
    salvata = (await r.a.foto(G, 1, "risaia"))[0]
    assert visti["originale"] == originale and salvata != originale
    assert max(Image.open(io.BytesIO(salvata)).size) <= al.LATO_FOTO  # la copia ricodificata e ridotta, non l'originale
    # troppo grande: rifiutata prima di leggerla
    grande = _allegato(b"x", dimensione=al.DIMENSIONE_FOTO_MASSIMA + 1)
    i = _i(fake_member(1))
    await AutoCog.foto.callback(cog, i, "risaia", grande)
    grande.read.assert_not_awaited()
    assert i.response.send_message.await_args.kwargs["ephemeral"] is True
    # auto non posseduta: rifiutata prima di leggerla
    non_mia = _allegato(png())
    i = _i(fake_member(1))
    await AutoCog.foto.callback(cog, i, "kitsune", non_mia)
    non_mia.read.assert_not_awaited()


@pytest.mark.asyncio
async def test_foto_non_immagine_o_sospetta_non_si_salva(r, monkeypatch):
    await r.lev.add_coins(G, 1, 500)
    await r.a.compra(G, 1, "risaia")
    cog = AutoCog(MagicMock())
    cog._rimborsi.cancel()
    # un eseguibile travestito da .png: il tipo vero lo decide dai primi byte e non dà nessuna copia
    i = _i(fake_member(1))
    await AutoCog.foto.callback(cog, i, "risaia", _allegato(b"MZ\x90\x00" + b"\x00" * 200, "auto.png", "image/png"))
    assert await r.a.foto(G, 1, "risaia") is None
    assert "ephemeral" in i.followup.send.await_args.kwargs
    # un PDF vero ha una scheda o una copia convertita, ma non è un'immagine: non si accetta
    i = _i(fake_member(1))
    await AutoCog.foto.callback(cog, i, "risaia", _allegato(b"%PDF-1.4\n%%EOF\n", "auto.pdf", "application/pdf"))
    assert await r.a.foto(G, 1, "risaia") is None


@pytest.mark.asyncio
async def test_comandi_di_gioco_compra_potenzia_gara_banco_e_staff(r, monkeypatch):
    cog = AutoCog(MagicMock())
    cog._rimborsi.cancel()
    u = fake_member(1)
    i = _i(u)
    await AutoCog.compra.callback(cog, i, "Risaia 600")  # senza monete
    assert i.response.send_message.await_args.kwargs["ephemeral"] is True
    await r.lev.add_coins(G, 1, 1000)
    i = _i(u)
    await AutoCog.compra.callback(cog, i, "risaia")
    assert i.response.send_message.await_args.kwargs["ephemeral"] is False and await _saldo(r, 1) == 850
    i = _i(u)
    await AutoCog.potenzia.callback(cog, i, "risaia", SimpleNamespace(value="motore", name="Motore"))
    assert await _saldo(r, 1) == 790
    i = _i(u)
    await AutoCog.gara.callback(cog, i, "risaia", None, 50)  # contro il banco niente puntata
    assert await _saldo(r, 1) == 790 and i.response.send_message.await_args.kwargs["ephemeral"] is True
    i = _i(u)
    await AutoCog.gara.callback(cog, i, "risaia", None, 0)
    i.followup.send.assert_awaited()
    assert [(x.corse) for x in await r.a.garage(G, 1)] == [1]
    i = _i(u)
    await AutoCog.gara.callback(cog, i, "risaia", None, 0)  # la pausa tra una gara e l'altra
    assert i.response.send_message.await_args.kwargs["ephemeral"] is True
    # sfida a un membro senza auto nel garage
    i = _i(u)
    await AutoCog.gara.callback(cog, i, "risaia", fake_member(2), 0)
    assert i.response.send_message.await_args.kwargs["ephemeral"] is True
    # garage e staff
    await r.a.imposta_foto(G, 1, "risaia", png(), "f" * 64)
    i = _i(fake_member(5))
    await AutoCog.togli_foto_staff.callback(cog, i, SimpleNamespace(id=1, mention="<@1>"), None)
    assert await r.a.foto(G, 1, "risaia") is None
    i = _i(u)
    await AutoCog.garage.callback(cog, i, None)
    assert "Risaia" in i.response.send_message.await_args.args[0]
