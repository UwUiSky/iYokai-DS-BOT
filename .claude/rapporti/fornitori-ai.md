# Tabella dei servizi AI

**Mai le chiavi qui.** Qui sta solo il nome della variabile del `.env`.
Si compila quando l'owner dà l'elenco dei servizi; ogni riga viene
dalla pagina ufficiale dei limiti e dei termini di quel servizio.

Tipi: `chat`, `testo`, `giudizio`, `codice`, `traduzione`, `confronto`,
`immagine`, `audio`, `musica`, `video`. Fascia: `bassa`, `media`,
`alta`.

| Servizio | Variabile della chiave | Tipi | Fascia | Richieste al minuto | Richieste al giorno | Token al minuto | Token al giorno | Rinnovo della quota | Può ricevere messaggi di utenti | Controllato il |
|---|---|---|---|---|---|---|---|---|---|---|
| *(in attesa dell'elenco dell'owner)* | | | | | | | | | | |

## Regole di scelta (riassunto; il disegno è in `agents/custode-ai.md`)

1. Cache e libreria prima di tutto.
2. Tra i servizi adatti al tipo: la fascia più bassa che basta, poi
   più quota rimasta.
3. Oltre l'85 % di una quota il servizio si salta fino al rinnovo.
4. Errore 429 o 5xx: pausa per quel servizio, si passa al successivo.
5. Testo con messaggi di utenti: solo servizi con "sì" nella penultima
   colonna.
