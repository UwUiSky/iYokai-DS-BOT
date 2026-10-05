"""
core/command_translator.py
==========================
Dà a Discord nomi e descrizioni tradotti dei comandi.
Funzioni coperte: SPEC §21 (NF-06)

STATO: scheletro. Il codice non è ancora scritto (issue #77).
"""

# ----------------------------------------------------------------------
# NOTA PER CHI SCRIVE QUESTO FILE — issue #77, fase F8
# Funzione: NF-06, Lingue italiano e inglese, e `/utility cerca-
#   comando`.
#
# Cosa deve fare la funzione: Tutti i testi del bot in un unico file per
#   lingua. La lingua del server decide le risposte. I nomi dei comandi
#   sono tradotti da Discord secondo la lingua dell'utente (D1). La
#   ricerca dei comandi capisce sinonimi in entrambe le lingue e mostra
#   solo i comandi che l'utente può usare.
# Questo file: Dà a Discord nomi e descrizioni tradotti dei comandi.
# Comandi previsti: /admin lingua, /utility cerca-comando.
# File collegati: locales/it.json, locales/en.json.
# File esistenti da toccare: core/i18n.py, core/command_search_logic.py,
#   cogs/utility/command_search.py, scripts/generate_command_list.py (da
#   estendere: scrive COMMAND_LIST_ITA.md e COMMAND_LIST_ENG.md).
# Test da scrivere per primi: tests/test_i18n_completo.py.
# Limiti da rispettare: Nome comando 32, descrizione 100, totale 8000
#   per comando anche con le traduzioni.
# Da chi prendere spunto: Maki (32 lingue), ProBot (10).
# Dipende da: NF-05 (i nomi cambiano lì). D1.
#
# Prima di iniziare: lista di controllo di
#   revisione/01-analisi/LIMITI.md (Parte 4); ogni impostazione passa da
#   un solo punto del codice, usato anche dal pannello web (decisione
#   D16); prima il test che fallisce, poi il codice.
# Dettaglio: revisione/02-piano/NUOVE_FUNZIONI.md e il catalogo in
#   revisione/01-analisi/catalogo/.
# ----------------------------------------------------------------------
