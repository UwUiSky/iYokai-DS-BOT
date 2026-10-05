"""
core/server_sync_logic.py
=========================
Cosa copiare tra due server collegati.
Funzioni coperte: SPEC §23 (NF-39)

STATO: scheletro. Il codice non è ancora scritto (issue #110).
"""

# ----------------------------------------------------------------------
# NOTA PER CHI SCRIVE QUESTO FILE — issue #110, fase F13
# Funzione: NF-39, Modelli di server e sincronia tra server.
#
# Cosa deve fare la funzione: Una raccolta di strutture pronte da
#   caricare. Ban e ruoli tenuti uguali tra due server dello stesso
#   proprietario.
# Questo file: Cosa copiare tra due server collegati.
# Comandi previsti: /admin backup modello …, /admin backup sincronia ….
# File esistenti da toccare: cogs/utility/backup.py.
# Test da scrivere per primi: tests/test_server_sync_logic.py.
# Limiti da rispettare: Stessi limiti del backup (LIM-28, LIM-38).
# Da chi prendere spunto: Xenon (5.731 modelli, sync).
# Dipende da: F3 finita (D8).
#
# Prima di iniziare: lista di controllo di
#   revisione/01-analisi/LIMITI.md (Parte 4); ogni impostazione passa da
#   un solo punto del codice, usato anche dal pannello web (decisione
#   D16); prima il test che fallisce, poi il codice.
# Dettaglio: revisione/02-piano/NUOVE_FUNZIONI.md e il catalogo in
#   revisione/01-analisi/catalogo/.
# ----------------------------------------------------------------------
