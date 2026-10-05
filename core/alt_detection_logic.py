"""
core/alt_detection_logic.py
===========================
Confronto delle impronte e punteggio.
Funzioni coperte: SPEC §4.2, §4.3 (NF-21)

STATO: scheletro. Il codice non è ancora scritto (issue #92).
"""

# ----------------------------------------------------------------------
# NOTA PER CHI SCRIVE QUESTO FILE — issue #92, fase F10
# Funzione: NF-21, Verifica su web e riconoscimento degli account doppi.
#
# Cosa deve fare la funzione: La verifica passa da una pagina web. Il
#   bot calcola un'impronta (mai l'IP in chiaro) e la confronta con
#   quelle già viste. Se trova un doppione avvisa lo staff: nessun ban
#   automatico tra server (scelta già presa).
# Questo file: Confronto delle impronte e punteggio.
# Comandi previsti: /security verify setup (opzione modo: web),
#   /security alt elenco.
# File collegati: cogs/security/alt_detection.py,
#   core/repositories/fingerprint_repo.py.
# File esistenti da toccare: cogs/security/verify.py.
# Test da scrivere per primi: tests/test_alt_detection.py.
# Migrazione: core/migrations/NNNN_fingerprints.sql. (prossimo numero
#   libero in core/migrations/).
# Limiti da rispettare: Dati personali: conservazione dichiarata,
#   comando privacy, cifratura a riposo.
# Da chi prendere spunto: Double Counter, Wick (modalità Web).
# Dipende da: NF-20. Privacy policy pubblicata. Scope OAuth identify
#   separato da guilds.join.
#
# Prima di iniziare: lista di controllo di
#   revisione/01-analisi/LIMITI.md (Parte 4); ogni impostazione passa da
#   un solo punto del codice, usato anche dal pannello web (decisione
#   D16); prima il test che fallisce, poi il codice.
# Dettaglio: revisione/02-piano/NUOVE_FUNZIONI.md e il catalogo in
#   revisione/01-analisi/catalogo/.
# ----------------------------------------------------------------------
