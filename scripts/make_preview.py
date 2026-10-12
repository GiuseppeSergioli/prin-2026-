#!/usr/bin/env python3
"""Build a self-contained, offline snapshot for reviewing the interface."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
html = (root / 'index.html').read_text(encoding='utf-8')
css = (root / 'styles.css').read_text(encoding='utf-8')
js = (root / 'app.js').read_text(encoding='utf-8')
data = json.loads((root / 'data/prin.json').read_text(encoding='utf-8'))

fetch_line = "const response = await fetch(`./data/prin.json?v=${Date.now()}`, {cache:'no-store'});"
assert fetch_line in js
js = js.replace(fetch_line, 'const response = {ok:true, json: async () => window.__PRIN_DATA__};')
data_js = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('<', r'\u003c')
html = html.replace('<link rel="stylesheet" href="./styles.css">', f'<style>{css}</style>')
html = html.replace('<script defer src="./app.js"></script>',
                    f'<script>window.__PRIN_DATA__={data_js};</script>\n'
                    f'<script>document.addEventListener("DOMContentLoaded",()=>{{{js}}});</script>')
html = html.replace('<body>', '<body><div style="background:#e6f4eb;color:#235b49;text-align:center;padding:8px 14px;font:700 12px Arial,sans-serif">ANTEPRIMA STATICA · La versione pubblicata aggiorna i dati automaticamente ogni sei ore</div>')
html = html.replace('I risultati pubblicati sono acquisiti automaticamente quando il sito ospitante esegue l’aggiornamento programmato.',
                    'Questa è una fotografia statica per esaminare l’interfaccia. La versione pubblicata aggiorna i dati automaticamente.')
(root / 'anteprima.html').write_text(html, encoding='utf-8')
print('Anteprima creata:', root / 'anteprima.html', len(html.encode('utf-8')), 'byte')
