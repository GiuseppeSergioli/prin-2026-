#!/usr/bin/env python3
"""Refresh the public PRIN dashboard from the MUR's funded-project annexes.

Run from any directory: python scripts/refresh.py [--force]. A failed source
never replaces a previously verified sector with an empty or partial result.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from lxml import html


ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "data" / "prin.json"
INDEX = {
    "ordinary": "https://prin.mur.gov.it/Pages/Index/301",
    "hybrid": "https://prin.mur.gov.it/Pages/Index/321",
}
MONEY = r"(?:\d{1,3}(?:\.\d{3})*|\d+),\d{2}"
CODE = r"2026[A-Z0-9]{6}"
ROW = re.compile(
    rf"(?<!\w)(\d{{1,2}})\s+(PI|RU)\s+(.+?)\s+({CODE}_\d{{3}})\s+"
    rf"(.+?)\s+(\d{{11}})\s+({MONEY})\s+({MONEY})\s+({MONEY})\s+({MONEY})(?!\d)",
    re.I | re.S,
)


def request(url: str) -> bytes:
    host = urllib.parse.urlsplit(url).hostname or ""
    if host not in {"prin.mur.gov.it", "mur.gov.it", "www.mur.gov.it"}:
        raise ValueError(f"Sorgente non autorizzata: {host}")
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; PRINObservatory/1.0; public-data-research)",
        "Accept": "text/html,application/pdf,*/*",
    })
    last_error = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=35) as response:
                if response.status != 200:
                    raise ValueError(f"HTTP {response.status}")
                return response.read(15_000_001)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Impossibile leggere {url}: {last_error}")


def norm(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def category(text: str, program: str) -> str | None:
    if program == "ordinary":
        match = re.search(r"\bSETTORE\s*(PE|LS|SH)\s*(\d{1,2})\b", text, re.I)
        return (match.group(1) + str(int(match.group(2)))).upper() if match else None
    if re.search(r"CYBERSICUREZZA", text, re.I):
        return "CYB"
    if re.search(r"INTELLIGENZA\s+ARTIFICIALE|\(IA\)", text, re.I):
        return "IA"
    match = re.search(r"LINEA\s+TEMATICA\s+(.+?)(?:\s*[-–]\s*(?:APPROVAZIONE|INDIVIDUAZIONE)|$)", text, re.I)
    if not match:
        return None
    plain = unicodedata.normalize("NFKD", match.group(1)).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]+", "-", plain.upper()).strip("-")[:35]


def discover(markup: bytes, program: str) -> list[dict]:
    doc = html.fromstring(markup)
    candidates = {}
    for a in doc.xpath('//a[@href]'):
        url = urllib.parse.urljoin(INDEX[program], a.get('href'))
        if urllib.parse.urlsplit(url).hostname not in {'mur.gov.it', 'www.mur.gov.it'}:
            continue
        if '/atti-e-normativa/' not in urllib.parse.urlsplit(url).path:
            continue
        parent = a.getparent()
        line = norm(parent.text_content() if parent is not None else a.text_content())
        sector = category(line, program)
        decree = re.search(r"\bn\s*[.°]?\s*(\d{1,5})\b", line, re.I)
        if not sector or not decree:
            continue
        item = {"program": program, "sector": sector, "decreto": decree.group(1), "page": url}
        previous = candidates.get(sector)
        if not previous or int(item['decreto']) > int(previous['decreto']):
            candidates[sector] = item
    if not candidates:
        raise ValueError(f"Nessun decreto riconosciuto nell'indice {program}")
    return list(candidates.values())


def annex_url(markup: bytes, page: str) -> str:
    doc = html.fromstring(markup)
    for a in doc.xpath('//a[@href]'):
        url = urllib.parse.urljoin(page, a.get('href'))
        label = urllib.parse.unquote(a.text_content() + ' ' + url.split('/')[-1])
        label = re.sub(r"[_\s]+", " ", label).lower()
        if (re.search(r"tabella\s*b\b", label) and 'finanziat' in label
                and url.lower().split('?')[0].endswith('.pdf')
                and urllib.parse.urlsplit(url).hostname in {'mur.gov.it', 'www.mur.gov.it'}):
            return url
    raise ValueError(f"Nessuna Tabella B dei progetti finanziati: {page}")


def euro(value: str) -> int:
    whole, cents = value.split(',')
    amount = int(whole.replace('.', ''))
    if cents != '00':
        raise ValueError(f"Importo con centesimi: {value}; serve aggiornare lo schema")
    return amount


def pdf_text(raw: bytes) -> list[str]:
    if not raw.startswith(b'%PDF'):
        raise ValueError("L'allegato ricevuto non è un PDF")
    with tempfile.NamedTemporaryFile(suffix='.pdf') as tmp:
        tmp.write(raw)
        tmp.flush()
        texts = []
        for mode in ['-raw', '-layout']:
            try:
                result = subprocess.run(['pdftotext', mode, '-enc', 'UTF-8', tmp.name, '-'],
                                        capture_output=True, text=True, check=True, timeout=35)
                texts.append(result.stdout)
            except (OSError, subprocess.SubprocessError):
                pass
        # Keep a second extraction engine available when the Poppler text
        # order changes after a ministry PDF export.
        try:
            import fitz
            with fitz.open(stream=raw, filetype='pdf') as doc:
                texts.extend('\n'.join(page.get_text(sort=sort) for page in doc) for sort in (False, True))
        except (ImportError, RuntimeError, ValueError):
            pass
        if not texts:
            raise ValueError('Nessun motore PDF disponibile')
        return texts


def project_titles(text: str) -> dict[str, str]:
    titles = {}
    for match in re.finditer(rf"(?m)^\s*\d{{1,2}}\.\s*({CODE})\s*[-–]\s*(.+?)\s*$", text):
        title = norm(match.group(2))
        if title and not title.lower().startswith('totale'):
            titles[match.group(1)] = title
    return titles


def parse_rows(text: str, item: dict, source: str, older: dict) -> list[dict]:
    # Flatten wrapped names and institutions; four amounts and the tax ID mark
    # the exact end of each unit. No subtotal matches this shape.
    compact = norm(text)
    titles = project_titles(text)
    units = []
    previous_names = {u['project']: u.get('titolo', '') for u in older.get('units', [])}
    for match in ROW.finditer(compact):
        index, role, person, code, ateneo, cf, cofinance, mur, cost, assigned = match.groups()
        if len(person) > 115 or len(ateneo) > 195 or int(index) > 35:
            continue
        cofinance, mur, cost, assigned = map(euro, (cofinance, mur, cost, assigned))
        if mur <= 0 or mur != assigned or cofinance + mur != cost:
            continue
        project = code.split('_')[0]
        units.append({
            "program": item['program'], "sector": item['sector'],
            "group": item['sector'][:2] if item['program'] == 'ordinary' else item['sector'],
            "decreto": item['decreto'], "role": role.upper(),
            "responsabile": norm(person), "unit": code, "project": project,
            "ateneo": norm(ateneo), "cf": cf, "mur": mur,
            "titolo": titles.get(project) or previous_names.get(project, ''), "source": source,
        })
    return units


def validate(units: list[dict], item: dict, previous: dict | None, rawtext: str) -> None:
    if not units:
        raise ValueError("Nessuna unità finanziata identificata")
    codes = [u['unit'] for u in units]
    if len(codes) != len(set(codes)):
        raise ValueError("Codici unità duplicati")
    projects = {u['project'] for u in units}
    for code in projects:
        if sum(u['role'] == 'PI' for u in units if u['project'] == code) != 1:
            raise ValueError(f"PI mancante o duplicato nel progetto {code}")
    # For the unchanged decree, any decline in records must be checked by a
    # person: an extraction that loses an entire project can otherwise pass.
    if previous and previous.get('decreto') == item['decreto']:
        if len(units) < int(previous.get('units', 0)):
            raise ValueError("Numero di unità inferiore alla precedente versione del decreto")
    total = sum(u['mur'] for u in units)
    if previous and previous.get('decreto') == item['decreto'] and total < previous.get('total', 0) * .75:
        raise ValueError("Totale molto inferiore alla versione precedente")
    if total <= 0 or not re.search(r"TOTALE\s+COMPLESSIVO", rawtext, re.I):
        raise ValueError("Totale complessivo del PDF non identificato")
    printed_total = f"{total:,}".replace(',', '.') + ',00'
    if printed_total not in rawtext:
        raise ValueError(f"La somma delle unità ({printed_total}) non compare nel totale dell'allegato")


def parse_annex(raw: bytes, item: dict, source: str, previous: dict | None, snapshot: dict) -> list[dict]:
    attempts = []
    for text in pdf_text(raw):
        rows = parse_rows(text, item, source, snapshot)
        try:
            validate(rows, item, previous, text)
            return rows
        except ValueError as exc:
            attempts.append(f"{len(rows)} righe: {exc}")
    raise ValueError("Estrazione non verificata (" + '; '.join(attempts) + ")")


def refresh(force: bool = False) -> dict:
    snapshot = json.loads(DEST.read_text(encoding='utf-8'))
    old_sources = {(s['program'], s['sector']): s for s in snapshot['sources']}
    old_units = {(u['program'], u['sector']): [] for u in snapshot['units']}
    for u in snapshot['units']:
        old_units[(u['program'], u['sector'])].append(u)
    sources, units, warnings, coverage = [], [], [], {'ordinary': [], 'hybrid': []}
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    for program, url in INDEX.items():
        try:
            discovered = discover(request(url), program)
        except Exception as exc:
            warnings.append(f"Indice {program}: {exc}")
            discovered = []
        known = {k: v for k, v in old_sources.items() if k[0] == program}
        for item in discovered:
            key = (program, item['sector'])
            previous = old_sources.get(key)
            if previous and key in known:
                del known[key]
            try:
                pdf = annex_url(request(item['page']), item['page'])
                content = request(pdf)
                fingerprint = hashlib.sha256(content).hexdigest()
                if (not force and previous and previous.get('decreto') == item['decreto']
                        and previous.get('sha256') == fingerprint):
                    current_units = old_units.get(key, [])
                    current_source = previous
                else:
                    current_units = parse_annex(content, item, pdf, previous, snapshot)
                    current_source = {**item, 'pdf': pdf, 'sha256': fingerprint,
                                      'total': sum(u['mur'] for u in current_units),
                                      'units': len(current_units),
                                      'projects': len({u['project'] for u in current_units}),
                                      'origin': 'MUR Tabella B'}
                    print(f"Acquisito {program}/{item['sector']}: {len(current_units)} unità")
            except Exception as exc:
                warnings.append(f"{program}/{item['sector']} (DD {item['decreto']}): {exc}")
                current_units = old_units.get(key, [])
                current_source = previous
            if current_source and current_units:
                sources.append(current_source)
                units.extend(current_units)
                coverage[program].append(item['sector'])
        # Preserve categories while the official index is temporarily down.
        for key, previous in known.items():
            sources.append(previous)
            units.extend(old_units.get(key, []))
            coverage[program].append(key[1])
            if discovered:
                warnings.append(f"{program}/{key[1]}: già acquisito, non più nell'indice; verifica richiesta")
    if not sources or not units:
        raise RuntimeError("Nessun risultato valido: conservata la fotografia precedente")
    snapshot.update({
        'checkedAt': now, 'sources': sorted(sources, key=lambda s: (s['program'], s['sector'])),
        'units': sorted(units, key=lambda u: (u['program'], u['sector'], u['project'], u['unit'])),
        'coverage': {k: sorted(v) for k, v in coverage.items()},
        'warnings': warnings,
    })
    if any(s.get('origin') == 'MUR Tabella B' for s in sources):
        snapshot['provenance'] = 'Tabelle B ufficiali MUR; i settori ancora in attesa di verifica conservano la trascrizione iniziale.'
    if not warnings:
        snapshot['asOf'] = now[:10]
        snapshot['provenance'] = 'Tabelle B ufficiali MUR, acquisite e verificate automaticamente.'
    temp = DEST.with_suffix('.tmp')
    temp.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    temp.replace(DEST)
    print(f"Totale: {len(units)} unità, {len(sources)} documenti; avvisi: {len(warnings)}")
    return snapshot


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--force', action='store_true', help='Rielabora anche i PDF invariati')
    args = parser.parse_args()
    refresh(args.force)
