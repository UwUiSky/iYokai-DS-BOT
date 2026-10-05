"""
core/activity_stats_logic.py
============================
Aggregazione per giorno e calcolo dei ruoli per attività.
Funzioni coperte: SPEC §23 (NF-25)

STATO: scheletro. Il codice non è ancora scritto (issue #96).
"""

# ----------------------------------------------------------------------
# NOTA PER CHI SCRIVE QUESTO FILE — issue #96, fase F13
# Funzione: NF-25, Statistiche di attività e ruoli per attività.
#
# Cosa deve fare la funzione: Messaggi e minuti in vocale per canale e
#   per membro, con grafici. Ruoli dati a chi è attivo in un periodo e
#   tolti a chi smette.
# Questo file: Aggregazione per giorno e calcolo dei ruoli per attività.
# Comandi previsti: /admin statistiche …, /utility serverstats.
# File collegati: cogs/utility/activity_stats.py,
#   core/repositories/activity_stats_repo.py.
# File esistenti da toccare: cogs/utility/server_stats.py.
# Test da scrivere per primi: tests/test_activity_stats.py.
# Migrazione: core/migrations/NNNN_activity_stats.sql. (prossimo numero
#   libero in core/migrations/).
# Limiti da rispettare: Tabelle che crescono: dati aggregati per giorno
#   e regola di pulizia (NF-04).
# Da chi prendere spunto: Statbot (Statroles).
# Dipende da: NF-04.
#
# Prima di iniziare: lista di controllo di
#   revisione/01-analisi/LIMITI.md (Parte 4); ogni impostazione passa da
#   un solo punto del codice, usato anche dal pannello web (decisione
#   D16); prima il test che fallisce, poi il codice.
# Dettaglio: revisione/02-piano/NUOVE_FUNZIONI.md e il catalogo in
#   revisione/01-analisi/catalogo/.
# ----------------------------------------------------------------------
