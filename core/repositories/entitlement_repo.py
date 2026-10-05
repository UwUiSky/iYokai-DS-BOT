"""
core/repositories/entitlement_repo.py
=====================================
Abbonamenti attivi per server.
Funzioni coperte: SPEC §3 (NF-22)

STATO: scheletro. Il codice non è ancora scritto (issue #93).
"""

# ----------------------------------------------------------------------
# NOTA PER CHI SCRIVE QUESTO FILE — issue #93, fase F10
# Funzione: NF-22, Pagamento vero del premium.
#
# Cosa deve fare la funzione: Il premium si compra davvero: abbonamento
#   dentro Discord (app premium) e, in alternativa, pagamento esterno
#   registrato dall'owner. Resta lo sblocco con le monete (1.000.000 per
#   modulo, SPEC §3.1) e con la cassa del server.
# Questo file: Abbonamenti attivi per server.
# Comandi previsti: /admin premium stato, /owner premium … (già
#   esistenti).
# File collegati: core/premium_entitlement_service.py.
# File esistenti da toccare: core/premium.py,
#   cogs/utility/owner_premium.py.
# Test da scrivere per primi: tests/test_premium_entitlement.py.
# Migrazione: core/migrations/NNNN_entitlements.sql. (prossimo numero
#   libero in core/migrations/).
# Limiti da rispettare: Per vendere dentro Discord l'app deve essere
#   verificata.
# Da chi prendere spunto: Tutti i grandi bot. Double Counter vende
#   tramite Discord.
# Dipende da: Verifica dell'app. I 6 moduli premium devono controllare
#   davvero il premium (F1).
#
# Prima di iniziare: lista di controllo di
#   revisione/01-analisi/LIMITI.md (Parte 4); ogni impostazione passa da
#   un solo punto del codice, usato anche dal pannello web (decisione
#   D16); prima il test che fallisce, poi il codice.
# Dettaglio: revisione/02-piano/NUOVE_FUNZIONI.md e il catalogo in
#   revisione/01-analisi/catalogo/.
# ----------------------------------------------------------------------
