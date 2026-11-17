"""
tests/test_allegati_copia.py
============================
Copia sicura di PDF, audio, video e testo (D74, #160) dalla decisione unica: file veri convertiti nel servizio della
sandbox (in questo processo, su un socket di prova); tetto di tempo giornaliero, video solo dove serve, playlist
travestite da video, file troppo grandi, sandbox ferma. Non solleva mai e non lascia file in quarantena.
Funzioni coperte: SPEC §8.16 (D74, #160)
"""

import re
import shutil

import pytest

from core import allegati_copia as ac
from core import immagini_pipeline as pl
from core import immagini_sandbox as sb
from core import immagini_servizio as servizio
from tests.support import conversioni_finte as c
from tests.test_immagini_pipeline import ambiente  # noqa: F401 - fixture: DB vero, quarantena in cartella di prova

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="serve ffmpeg")
GUILD = 777000870
PROIBITE = re.compile(rb"/(JavaScript|JS|OpenAction|AA|EmbeddedFiles?|URI|Names)(?![A-Za-z0-9_])")


@pytest.fixture
async def attivo(ambiente, tmp_path, monkeypatch):  # noqa: F811
    percorso = str(tmp_path / "sbx.sock")
    monkeypatch.setenv(sb.VARIABILE_SOCKET, percorso)
    server = await servizio.serve(percorso)
    ac.azzera_tempo()
    yield ambiente
    server.close()
    await server.wait_closed()
    ac.azzera_tempo()


def _vuota(cartella) -> bool:
    return not cartella.exists() or not list(cartella.iterdir())


async def test_pdf_pericoloso_torna_rifatto(attivo):
    _, quar, _ = attivo
    copia, d = await pl.esamina_allegato(c.pdf_pericoloso(), "contratto.pdf", "application/pdf", GUILD)
    assert d.tipo.categoria == "pdf" and copia is not None and copia[0] == "contratto.pdf"
    assert copia[1].startswith(b"%PDF-") and not PROIBITE.search(copia[1])
    assert _vuota(quar)
    assert ac.secondi_usati(GUILD) > 0


async def test_audio_torna_ogg_e_testo_torna_txt(attivo, tmp_path):
    copia, _ = await pl.esamina_allegato(c.audio(tmp_path), "voce.wav", "audio/wav", GUILD)
    assert copia is not None and copia[0] == "voce.ogg" and copia[1].startswith(b"OggS")
    copia, d = await pl.esamina_allegato(("ciao\r\n" * 50 + "mondo\x1b").encode(), "appunti.md", "text/markdown", GUILD)
    assert d.azione == "scheda" and copia == ("appunti.txt", ("ciao\n" * 50 + "mondo").encode())


async def test_audio_lungo_si_dice_tagliato_nel_nome(attivo, tmp_path):
    copia, _ = await pl.esamina_allegato(c.audio(tmp_path, secondi=620), "lunga.wav", "audio/wav", GUILD)
    assert copia is not None and copia[0] == "lunga-tagliato.ogg"


async def test_il_video_solo_dove_lo_chiede_il_chiamante(attivo, tmp_path):
    video = c.video(tmp_path, larghezza=320, altezza=180)
    copia, d = await pl.esamina_allegato(video, "clip.mp4", "video/mp4", GUILD)
    assert d.tipo.categoria == "video" and copia is None  # log di massa: solo scheda
    copia, _ = await pl.esamina_allegato(video, "clip.mp4", "video/mp4", GUILD, con_video=True)
    assert copia is not None and copia[0] == "clip.mp4" and copia[1][4:8] == b"ftyp" and len(copia[1]) < ac.MAX_USCITA


@pytest.mark.parametrize("dati", [b"#EXTM3U\n#EXTINF:5,\nfile:///etc/passwd\n", b"ffconcat version 1.0\nfile '/etc/passwd'\n"])
async def test_playlist_travestita_da_video_non_arriva_a_ffmpeg(attivo, monkeypatch, dati):
    chiamate = []
    originale = sb.converti

    async def spia(*a, **k):
        chiamate.append(a)
        return await originale(*a, **k)

    monkeypatch.setattr(sb, "converti", spia)
    for nome in ("video.mp4", "musica.mp3", "lista.txt"):
        copia, _ = await pl.esamina_allegato(dati, nome, None, GUILD, con_video=True)
        assert copia is None or nome == "lista.txt"
    assert all(a[0] == "testo" for a in chiamate)  # al massimo come testo, mai come media


async def test_script_con_estensione_pericolosa_resta_rifiutato(attivo):
    copia, d = await pl.esamina_allegato(b"print('ciao')\n" * 50, "script.py", "text/x-python", GUILD)
    assert copia is None and d.azione == "rifiuta"


async def test_tetto_giornaliero_di_tempo_poi_solo_scheda(attivo, monkeypatch):
    class Archivio:
        async def get_guild_setting(self, guild_id, chiave, predefinito=None):
            return 1 if chiave == ac.SETTING_SECONDI_GIORNO else predefinito

    from core import database

    monkeypatch.setattr(database.db, "get_guild_setting", Archivio().get_guild_setting)
    ac._usati[(GUILD, ac._giorno())] = 5.0
    copia, _ = await pl.esamina_allegato(b"testo normale\n", "a.txt", None, GUILD)
    assert copia is None
    ac.azzera_tempo()
    copia, _ = await pl.esamina_allegato(b"testo normale\n", "a.txt", None, GUILD)
    assert copia is not None
    assert ac.secondi_usati(GUILD + 1) == 0  # il tempo e' per server


async def test_tetto_a_zero_spegne_le_conversioni(attivo, monkeypatch):
    from core import database

    async def zero(guild_id, chiave, predefinito=None):
        return 0 if chiave == ac.SETTING_SECONDI_GIORNO else predefinito

    monkeypatch.setattr(database.db, "get_guild_setting", zero)
    assert (await pl.esamina_allegato(b"testo normale\n", "a.txt", None, GUILD))[0] is None


async def test_impostazione_storta_vale_il_predefinito(attivo, monkeypatch):
    from core import database

    async def storta(guild_id, chiave, predefinito=None):
        return "tanto"

    monkeypatch.setattr(database.db, "get_guild_setting", storta)
    assert await ac.tetto_secondi(GUILD) == ac.SECONDI_GIORNO_PREDEFINITI


async def test_file_troppo_grande_o_copia_troppo_grande_non_da_copia(attivo, monkeypatch):
    monkeypatch.setitem(ac.MAX_ENTRATA, "testo", 10)
    assert (await pl.esamina_allegato(b"x" * 100, "a.txt", None, GUILD))[0] is None
    monkeypatch.setitem(ac.MAX_ENTRATA, "testo", 1000)
    monkeypatch.setattr(ac, "MAX_USCITA", 5)
    assert (await pl.esamina_allegato(b"x" * 100, "a.txt", None, GUILD))[0] is None


async def test_sandbox_ferma_o_che_cade_non_da_copia_e_non_lascia_file(attivo, monkeypatch):
    _, quar, _ = attivo
    monkeypatch.setenv(sb.VARIABILE_SOCKET, str(quar.parent / "non-c-e.sock"))
    assert (await pl.esamina_allegato(b"testo normale\n", "a.txt", None, GUILD))[0] is None

    async def cade(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(sb, "converti", cade)
    assert (await pl.esamina_allegato(b"testo normale\n", "a.txt", None, GUILD))[0] is None
    assert _vuota(quar)


async def test_pdf_storto_non_da_copia(attivo):
    copia, d = await pl.esamina_allegato(b"%PDF-1.4\n" + bytes(range(256)) * 8, "x.pdf", "application/pdf", GUILD)
    assert copia is None and d.tipo.categoria == "pdf"


# ------------------------------------------------------------------ log dei messaggi (allegati_sicuri)
@pytest.fixture
def cartella_log(attivo, tmp_path, monkeypatch):
    from core import allegati_sicuri as al

    monkeypatch.setenv(al.VARIABILE_CARTELLA, str(tmp_path / "all"))
    return al


async def test_log_conserva_la_copia_di_pdf_audio_e_testo_ma_non_del_video(cartella_log, tmp_path):
    al = cartella_log
    pdf = await al.salva(GUILD, 1, 2, 3, "log", "rel.pdf", c.pdf_pericoloso(), content_type="application/pdf")
    assert pdf.stato == al.STATO_SALVATA and pdf.con_file and pdf.tipo == "pdf" and pdf.anteprima is None
    nome, dati = await al.leggi(pdf.id)
    assert nome == "rel.pdf" and not PROIBITE.search(dati) and b"segreto" not in dati

    audio = await al.salva(GUILD, 1, 2, 3, "log", "voce.wav", c.audio(tmp_path), content_type="audio/wav")
    assert audio.stato == al.STATO_SALVATA and (await al.leggi(audio.id))[0] == "voce.ogg"

    testo = await al.salva(GUILD, 1, 2, 3, "log", "n.txt", b"ciao\r\nmondo\n", content_type="text/plain")
    assert testo.stato == al.STATO_SALVATA and await al.leggi(testo.id) == ("n.txt", b"ciao\nmondo\n")

    video = await al.salva(GUILD, 1, 2, 3, "log", "v.mp4", c.video(tmp_path, larghezza=160, altezza=90), content_type="video/mp4")
    assert video.stato == al.STATO_SCHEDA and not video.con_file and video.tipo == "video"
    # sul disco ci sono solo le tre copie convertite: mai un originale
    contenuti = [p.read_bytes() for p in (tmp_path / "all").iterdir()]
    assert len(contenuti) == 3 and not any(b"app.alert" in x or b"nascosto.txt" in x for x in contenuti)


async def test_log_senza_sandbox_resta_la_scheda(cartella_log, monkeypatch, tmp_path):
    monkeypatch.setenv(sb.VARIABILE_SOCKET, str(tmp_path / "non-c-e.sock"))
    copia = await cartella_log.salva(GUILD, 1, 2, 3, "log", "rel.pdf", c.pdf_semplice())
    assert copia.stato == cartella_log.STATO_SCHEDA and not copia.con_file
