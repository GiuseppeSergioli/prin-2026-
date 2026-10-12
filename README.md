# PRIN 2026 · Osservatorio delle sedi beneficiarie

Dashboard pubblica per PRIN 2026 e PRIN Hybrid: filtri per bando, area ERC e settore o linea tematica, ricerca, graduatoria per sede, dettaglio dei progetti, quote PI/RU ed esportazione CSV. È un sito statico senza registrazione, pensato per GitHub Pages.

## Avvio locale

```bash
python3 -m http.server 8000
```

Apri `http://localhost:8000/` dalla cartella di questo progetto. La pagina legge `data/prin.json`; la semplice apertura del file HTML dal disco non abilita la lettura del JSON in tutti i browser.

Per una dimostrazione senza server, apri `anteprima.html`: incorpora la fotografia iniziale e consente di provare filtri, classifiche, dettagli ed esportazione. Non è la versione che si aggiorna nel tempo.

## Pubblicazione e aggiornamento

1. Crea un repository **pubblico** su GitHub e carica **il contenuto di questa cartella** nella radice del branch `main`.
2. In **Settings → Pages → Build and deployment** seleziona **GitHub Actions** come sorgente.
3. In **Settings → Actions → General**, assicurati che il workflow abbia permesso di scrittura sul repository. Avvia **Actions → Aggiorna e pubblica PRIN 2026 → Run workflow**.
4. Il link pubblico sarà mostrato nel job `github-pages`, normalmente `https://<utente>.github.io/<repository>/`. Da quel momento il controllo automatico gira ogni sei ore (orario UTC); la pagina aperta controlla il JSON ogni 30 minuti.

La pipeline legge [l'indice PRIN 2026](https://prin.mur.gov.it/Pages/Index/301) e [l'indice Hybrid](https://prin.mur.gov.it/Pages/Index/321), individua per ogni settore o linea l'atto vigente e la **Tabella B dei progetti finanziati**, poi legge le quote MUR per ogni unità. La scelta del decreto più recente per la stessa categoria evita di sommare il DD 32 PE7 al DD 45 che lo sostituisce. I codici unità, il ruolo, la quadratura dei costi, un PI per progetto e il totale di unità rispetto alla versione precedente sono verificati prima di sostituire i dati. Se una fonte fallisce, l'ultimo risultato acquisito resta disponibile e l'interfaccia espone l'avviso; un nuovo settore non viene rappresentato come zero.

I workflow programmati di GitHub possono partire in ritardo ed essere disabilitati dopo lunghi periodi di inattività del repository. Un cambio nel formato dei PDF o un blocco delle richieste dai runner richiede intervento: controlla gli avvisi visibili nella sezione **Metodo e fonti** e i log di Actions. È possibile rilanciare manualmente il workflow.

## Significato dei conteggi

- **Sede**: ateneo o ente riportato nell'allegato, unificato per codice fiscale; i campus fisici non sono distinguibili con certezza dai dati disponibili.
- **Progetti**: codici progetto distinti con almeno una unità della sede nella selezione corrente. PI e RU sono conteggi distinti per ruolo; il totale deduplica se una stessa sede partecipa in entrambi i ruoli.
- **Finanziamento**: somma della colonna *contributo MUR assegnato* alle singole unità della sede, separabile per ruolo; non comprende il cofinanziamento né attribuisce a ogni sede l'intero importo del progetto.
- **Area Hybrid**: “Trasversale”; il settore del filtro è la linea tematica, dato che la Tabella B non attribuisce una singola area ERC comparabile a ogni progetto Hybrid.

La fotografia iniziale è del **9 ottobre 2026**: 18 settori PRIN ordinari (726 unità, 144 progetti, 155.398.008 €) e due linee Hybrid (92 unità, 17 progetti, 23.197.367 €). È basata sulla [trascrizione pubblica di MODAL / Università di Napoli Federico II](https://www.labdma.unina.it/AtlantePrin2026/), con per ogni riga il collegamento all'allegato MUR. Sono state riutilizzate solo le colonne contenute nei documenti ministeriali; interfaccia, codice e aggregazioni sono nuovi. Il portale ministeriale elenca anche il DD 50 (LS6) del **12 ottobre 2026**, non incluso nella fotografia iniziale: la pipeline lo acquisirà quando il suo allegato sarà raggiungibile e supererà le verifiche.

La fonte ufficiale prevale per ogni verifica amministrativa. Gli importi sono assegnazioni, non importi già erogati.

## Verifica

```bash
python3 -m unittest discover -s tests -v
python3 scripts/refresh.py
```

Il secondo comando richiede accesso Internet alle pagine e ai PDF del MUR; se le fonti non sono raggiungibili, conserva il dataset precedente e aggiunge un avviso. Richiede Python 3.12, `pip install -r requirements.txt`; `pdftotext` migliora la lettura dei PDF, con PyMuPDF come alternativa.
