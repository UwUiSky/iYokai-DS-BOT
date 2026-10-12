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
