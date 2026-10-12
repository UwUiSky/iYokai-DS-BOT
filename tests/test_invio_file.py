"""
M 14.7 (LIM-55): discord.py crede a 10 MiB, ma il limite vero dipende dal
server. Una funzione comune manda un file, lo divide oltre la soglia o lo
rifiuta.
"""

import pytest

from core.invio_file import FILE_MAX_BYTE, FileTroppoGrande, dividi_in_parti, invia_file

MIB = 1024 * 1024


def test_file_piccolo_resta_intero():
    assert dividi_in_parti(b"ciao", "a.txt") == [("a.txt", b"ciao")]


def test_file_da_12_mib_viene_diviso_sotto_la_soglia():
    parti = dividi_in_parti(b"x" * (12 * MIB), "dati.json")
    assert len(parti) == 2
    assert all(len(dati) <= FILE_MAX_BYTE for _, dati in parti)
    assert b"".join(d for _, d in parti) == b"x" * (12 * MIB)
    assert [n for n, _ in parti] == ["dati.part1.json", "dati.part2.json"]


def test_il_testo_si_divide_a_fine_riga():
    riga = ("a" * 99 + "\n").encode()
    dati = riga * 200
    parti = dividi_in_parti(dati, "log.txt", limite=1000)
    assert b"".join(d for _, d in parti) == dati
    assert all(d.endswith(b"\n") for _, d in parti)
    assert all(len(d) <= 1000 for _, d in parti)


def test_una_riga_piu_lunga_del_limite_si_taglia_comunque():
    parti = dividi_in_parti(b"z" * 2500, "a.txt", limite=1000)
    assert [len(d) for _, d in parti] == [1000, 1000, 500]


@pytest.mark.asyncio
async def test_invia_file_manda_una_parte_per_messaggio():
    inviati = []

    async def invia(contenuto=None, **kw):
        inviati.append((contenuto, kw["file"].filename, kw.get("ephemeral")))

    n = await invia_file(invia, b"x" * (12 * MIB), "dati.json", contenuto="Ecco", ephemeral=True)

    assert n == 2
    assert inviati[0] == ("Ecco", "dati.part1.json", True)
    assert inviati[1][0] is None and inviati[1][1] == "dati.part2.json"


@pytest.mark.asyncio
async def test_senza_divisione_un_file_troppo_grande_viene_rifiutato():
    async def invia(contenuto=None, **kw):
        raise AssertionError("non va inviato")

    with pytest.raises(FileTroppoGrande):
        await invia_file(invia, b"x" * (12 * MIB), "a.bin", dividi=False)


@pytest.mark.asyncio
async def test_troppe_parti_vengono_rifiutate():
    async def invia(contenuto=None, **kw):
        raise AssertionError("non va inviato")

    with pytest.raises(FileTroppoGrande):
        await invia_file(invia, b"x" * 30, "a.bin", limite=1, max_parti=5)


def test_il_bordo_del_limite_e_incluso():
    assert dividi_in_parti(b"x" * 10, "a.bin", limite=10) == [("a.bin", b"x" * 10)]  # esattamente al limite: intero
    assert len(dividi_in_parti(b"x" * 11, "a.bin", limite=10)) == 2


def test_un_a_capo_in_testa_alla_parte_non_produce_una_parte_di_un_byte():
    parti = dividi_in_parti(b"\n" + b"x" * 30, "a.txt", limite=10)
    assert [len(d) for _, d in parti][0] == 10
    assert b"".join(d for _, d in parti) == b"\n" + b"x" * 30


@pytest.mark.asyncio
async def test_su_interazione_la_prima_parte_risponde_le_altre_vanno_in_followup():
    from types import SimpleNamespace

    from core.invio_file import invia_file_su_interazione

    visti = []

    async def risposta(testo, **kw):
        visti.append(("response", testo, kw["file"].filename))

    async def seguito(testo, **kw):
        visti.append(("followup", testo, kw["file"].filename))

    interazione = SimpleNamespace(
        response=SimpleNamespace(is_done=lambda: False, send_message=risposta),
        followup=SimpleNamespace(send=seguito),
    )

    n = await invia_file_su_interazione(interazione, b"x" * 25, "a.txt", contenuto="Ecco", limite=10, ephemeral=True)

    assert n == 3
    assert [v[0] for v in visti] == ["response", "followup", "followup"]
    assert visti[0][1] == "Ecco" and visti[1][1] is None


@pytest.mark.asyncio
async def test_su_interazione_senza_divisione_un_file_grande_non_parte():
    from types import SimpleNamespace

    from core.invio_file import invia_file_su_interazione

    async def mai(*a, **k):
        raise AssertionError("non va inviato")

    interazione = SimpleNamespace(
        response=SimpleNamespace(is_done=lambda: False, send_message=mai), followup=SimpleNamespace(send=mai)
    )
    with pytest.raises(FileTroppoGrande):
        await invia_file_su_interazione(interazione, b"x" * 25, "a.json", limite=10, dividi=False)
