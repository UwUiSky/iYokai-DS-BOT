"""
tests/test_immagini_sandbox.py
==============================
Sandbox con processi veri (D62): limiti di memoria, di CPU e di tempo vero, uscita enorme,
immagine buona, bomba di pixel; coda con tetti totale e per server.
"""

import asyncio
import sys

import pytest

from core import immagini_coda as coda_mod
from core import immagini_quarantena as q
from core import immagini_sandbox as sb
from tests.support import immagini_finte as f

PICCOLI = sb.Limiti(memoria=256 * 1024 * 1024, cpu=1, reale=3.0)


def py(codice: str) -> list[str]:
    return [sys.executable, "-I", "-B", "-c", codice]


@pytest.fixture
def cartella(tmp_path, monkeypatch):
    monkeypatch.setenv(q.VARIABILE_CARTELLA, str(tmp_path))
    return tmp_path


def _metti(cartella, dati: bytes, nome="a" * 32) -> str:
    (cartella / nome).write_bytes(dati)
    return nome


@pytest.mark.asyncio
async def test_bomba_di_memoria_viene_uccisa():
    r = await sb.esegui_locale("a" * 32, PICCOLI, py("x = bytearray(2 * 1024**3); print('vivo')"))
    assert r.esito == "ucciso"


@pytest.mark.asyncio
async def test_ciclo_di_cpu_viene_ucciso_dal_limite_di_cpu():
    r = await sb.esegui_locale("a" * 32, sb.Limiti(cpu=1, reale=6.0), py("while True: pass"))
    assert r.esito == "ucciso"


@pytest.mark.asyncio
async def test_attesa_troppo_lunga_viene_uccisa_dal_tempo_vero():
    r = await sb.esegui_locale("a" * 32, sb.Limiti(cpu=4, reale=1.0), py("import time; time.sleep(30)"))
    assert r.esito == "ucciso_tempo"


@pytest.mark.asyncio
async def test_figlio_che_chiude_l_uscita_e_resta_vivo_viene_ucciso_dal_tempo_vero():
    # Un figlio compromesso chiude stdout e dorme: senza tetto sull'attesa la coda resterebbe ferma per sempre.
    codice = "import os, time; os.close(1); time.sleep(30)"
    r = await asyncio.wait_for(sb.esegui_locale("a" * 32, sb.Limiti(cpu=4, reale=1.0), py(codice)), 10)
    assert r.esito == "ucciso_tempo"


@pytest.mark.asyncio
async def test_uscita_enorme_viene_fermata():
    r = await sb.esegui_locale(
        "a" * 32, PICCOLI, py("import sys\nwhile True: sys.stdout.buffer.write(b'x' * 1000000)")
    )
    assert r.esito == "uscita_enorme"


@pytest.mark.asyncio
async def test_il_figlio_non_puo_scrivere_file(tmp_path):
    bersaglio = tmp_path / "scritto"
    r = await sb.esegui_locale(
        "a" * 32, PICCOLI, py(f"open({str(bersaglio)!r}, 'wb').write(b'x' * 10)")
    )
    assert r.esito == "ucciso" and not bersaglio.exists() or bersaglio.stat().st_size == 0


@pytest.mark.asyncio
async def test_nome_non_valido_non_avvia_nulla():
    with pytest.raises(ValueError):
        await sb.esegui_locale("../../etc/passwd")


@pytest.mark.asyncio
async def test_immagine_buona_con_il_worker_vero(cartella):
    nome = _metti(cartella, f.png(50, 40))
    r = await sb.analizza(nome)
    assert r.riuscita and r.info["formato"] == "PNG" and (r.info["larghezza"], r.info["altezza"]) == (50, 40)
    assert r.info["motivi"] == []


@pytest.mark.asyncio
async def test_gif_animata_conta_i_fotogrammi(cartella):
    nome = _metti(cartella, f.gif_animata(7))
    r = await sb.analizza(nome)
    assert r.riuscita and r.info["fotogrammi"] == 7


@pytest.mark.asyncio
async def test_bomba_di_pixel_e_rifiutata_dal_worker(cartella):
    nome = _metti(cartella, f.png_dichiarato(60000, 60000))
    r = await sb.analizza(nome)
    assert r.esito == "errore" and r.info["motivo"] == "troppo_grande"


@pytest.mark.asyncio
async def test_file_che_non_e_un_immagine_e_errore_non_crash(cartella):
    nome = _metti(cartella, b"questo non e' un'immagine" * 10)
    r = await sb.analizza(nome)
    assert r.esito == "errore" and r.info["motivo"] == "decodifica"


@pytest.mark.asyncio
async def test_file_mancante_e_errore(cartella):
    r = await sb.analizza("c" * 32)
    assert r.esito == "errore"


@pytest.mark.asyncio
async def test_coda_rispetta_i_tetti():
    c = coda_mod.CodaImmagini(max_totale=3, max_per_server=2)
    via = asyncio.Event()

    async def lungo():
        await via.wait()
        return 1

    t1 = asyncio.create_task(c.esegui(1, lungo))
    t2 = asyncio.create_task(c.esegui(1, lungo))
    await asyncio.sleep(0)
    with pytest.raises(coda_mod.CodaPiena):  # il server 1 ha gia' 2
        await c.esegui(1, lungo)
    t3 = asyncio.create_task(c.esegui(2, lungo))
    await asyncio.sleep(0)
    assert c.in_coda == 3
    with pytest.raises(coda_mod.CodaPiena):  # tre in tutto
        await c.esegui(3, lungo)
    via.set()
    assert await asyncio.gather(t1, t2, t3) == [1, 1, 1]
    assert c.in_coda == 0 and c.in_coda_per(1) == 0


@pytest.mark.asyncio
async def test_coda_un_lavoro_alla_volta_e_si_libera_anche_con_errore():
    c = coda_mod.CodaImmagini()
    attivi, massimo = 0, 0

    async def lavoro():
        nonlocal attivi, massimo
        attivi += 1
        massimo = max(massimo, attivi)
        await asyncio.sleep(0.01)
        attivi -= 1

    async def rotto():
        raise RuntimeError("boom")

    await asyncio.gather(*(c.esegui(1, lavoro) for _ in range(5)))
    assert massimo == 1
    with pytest.raises(RuntimeError):
        await c.esegui(1, rotto)
    assert c.in_coda == 0


def test_avviso_all_owner_al_massimo_ogni_10_minuti():
    c = coda_mod.CodaImmagini()
    assert c.puo_avvisare() is True
    assert c.puo_avvisare() is False


@pytest.mark.asyncio
async def test_servizio_su_socket_da_lo_stesso_esito_del_modo_ridotto(cartella, tmp_path, monkeypatch):
    from core import immagini_servizio as servizio

    percorso = str(tmp_path / "sbx" / "sock")
    monkeypatch.setenv(sb.VARIABILE_SOCKET, percorso)
    server = await servizio.serve(percorso)
    try:
        nome = _metti(cartella, f.png(60, 20))
        r = await sb.analizza(nome)
        assert r.modo == sb.MODO_SERVIZIO and r.riuscita and (r.info["larghezza"], r.info["altezza"]) == (60, 20)
        assert r.png.startswith(b"\x89PNG") and r.info["dhash"]
        cattiva = _metti(cartella, f.png_dichiarato(60000, 60000), "b" * 32)
        r2 = await sb.analizza(cattiva)
        assert r2.modo == sb.MODO_SERVIZIO and r2.esito == "errore" and r2.info["motivo"] == "troppo_grande"
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_servizio_rifiuta_nomi_strani(tmp_path, monkeypatch):
    from core import immagini_servizio as servizio

    percorso = str(tmp_path / "s" / "sock")
    server = await servizio.serve(percorso)
    try:
        lettore, scrittore = await asyncio.open_unix_connection(percorso)
        scrittore.write(b"../../etc/passwd\n")
        grezzo = await lettore.read()
        info, _ = sb.leggi_uscita(grezzo)
        assert info["stato"] == "errore" and info["info"]["motivo"] == "nome"
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_senza_servizio_si_ripiega_sulla_sandbox_ridotta(cartella, tmp_path, monkeypatch):
    monkeypatch.setenv(sb.VARIABILE_SOCKET, str(tmp_path / "non-esiste"))
    r = await sb.analizza(_metti(cartella, f.png()))
    assert r.riuscita and r.modo == sb.MODO_RIDOTTA


@pytest.mark.asyncio
async def test_socket_morto_ripiega_senza_errori(cartella, tmp_path, monkeypatch):
    morto = tmp_path / "morto"
    morto.write_bytes(b"")  # esiste, ma nessuno ascolta
    monkeypatch.setenv(sb.VARIABILE_SOCKET, str(morto))
    r = await sb.analizza(_metti(cartella, f.png()))
    assert r.riuscita and r.modo == sb.MODO_RIDOTTA


@pytest.mark.asyncio
async def test_servizio_che_non_risponde_dopo_il_lavoro_non_ripiega_sulla_sandbox_ridotta(cartella, tmp_path, monkeypatch):
    # Il servizio ha preso l'immagine e poi tace: rifarla nella sandbox ridotta darebbe all'attacco un secondo
    # tentativo con meno isolamento. Esito sospetto, modo servizio.
    percorso = str(tmp_path / "muto")
    fine = asyncio.Event()

    async def muto(lettore, scrittore):
        await lettore.readline()
        await fine.wait()
        scrittore.close()

    server = await asyncio.start_unix_server(muto, path=percorso)
    monkeypatch.setenv(sb.VARIABILE_SOCKET, percorso)

    async def locale(*a, **k):
        raise AssertionError("ripiego locale non atteso")

    monkeypatch.setattr(sb, "esegui_locale", locale)
    try:
        r = await asyncio.wait_for(sb.analizza(_metti(cartella, f.png()), sb.Limiti(reale=0.2)), 15)
        assert r.modo == sb.MODO_SERVIZIO and r.esito == "ucciso_tempo"
    finally:
        fine.set()
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_worker_senza_pillow_e_sandbox_non_disponibile_non_malevola(cartella):
    # Un interprete senza Pillow (per esempio l'unita' con il python di sistema e non quello del bot) non deve
    # far diventare malevola ogni immagine: e' la sandbox che manca.
    nome = _metti(cartella, f.png())
    codice = (
        "import sys, runpy; sys.modules['PIL'] = None; "
        f"sys.argv = ['w', {nome!r}]; runpy.run_path({str(sb.WORKER)!r}, run_name='__main__')"
    )
    r = await sb.esegui_locale(nome, comando=py(codice))
    assert r.esito == "non_disponibile"
