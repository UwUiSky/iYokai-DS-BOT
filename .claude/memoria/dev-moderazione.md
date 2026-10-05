# Memoria di dev-moderazione

## Aggiornata
05/10/2026 · ramo `main` · ultimo commit `3dc9031`

## In corso
- Niente a metà.

## Fatto
- F1, sicurezza + AutoMod + verifica: unito su main con `7722b71`
  (nuovo `core/security_access.py`, tabella `anti_raid_lockdown`).
- Voci rapide F1 (anti-nuke non conta il bot, anti-raid ignora i bot).

## Cose imparate
- Le tabelle di sicurezza stanno in `security_repo.run_migrations`.
- Dopo il giro del 05/10 il messaggio privato di kick/ban parte dopo
  l'azione: va riportato prima (vedi Aperto).

## Aperto
- #137: messaggio privato **prima** di kick, ban, tempban, softban; si
  cancella se l'azione fallisce (`actions.py`, `softban_mute.py`,
  `_shared.py: try_dm`).
- #133 (tutto il blocco che segue). Anti-nuke: cancellazioni sotto soglia mai recuperate; ruoli
  ripristinati senza posizione né membri; tag dei forum persi.
- Anti-raid: un avviso per ogni ingresso; ruolo "Quarantined" già
  esistente non aggiornato.
- AutoMod: liste dei link senza tetto. Verifica: configurazione senza
  cache.
- M 10.16: sospendere i benvenuti privati durante un raid.
- #138: ban temporaneo con rientro (invito e ruoli) e isolamento.
