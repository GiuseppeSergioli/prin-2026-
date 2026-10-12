import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from refresh import category, discover, parse_annex, parse_rows, validate  # noqa: E402


class RefreshTest(unittest.TestCase):
    def test_replacement_decree_wins(self):
        html = b'''<div>
          <p>BANDO PRIN 2026 <a href="https://www.mur.gov.it/it/atti-e-normativa/32">DDG n. 32 - MACROSETTORE PE - SETTORE PE7</a> - annullato</p>
          <p>BANDO PRIN 2026 <a href="https://www.mur.gov.it/it/atti-e-normativa/45">DDG n. 45 - MACROSETTORE PE - SETTORE PE7</a> - sostituisce 32</p>
          <p>BANDO PRIN 2026 <a href="https://www.mur.gov.it/it/atti-e-normativa/50">DDG n. 50 - MACROSETTORE LS - SETTORE LS6</a></p>
        </div>'''
        found = {item['sector']: item['decreto'] for item in discover(html, 'ordinary')}
        self.assertEqual(found, {'PE7': '45', 'LS6': '50'})
        self.assertEqual(category('LINEA TEMATICA INTELLIGENZA ARTIFICIALE (IA)', 'hybrid'), 'IA')

    def test_wrapped_units_and_local_funding(self):
        raw = '''PE1 - Tabella B - Progetti finanziati
        1 PI VERDI Ada 2026ABCDEF_001 Universita degli Studi di ESEMPIO
        12345678901 100.000,00 200.000,00 300.000,00 200.000,00
        2
        RU ROSSI Luca
        2026ABCDEF_002 Ateneo Secondo 12345678902 80.000,00 120.000,00 200.000,00 120.000,00
        1. 2026ABCDEF - Un progetto di prova
        TOTALE COMPLESSIVO 320.000,00
        '''
        item = {'program': 'ordinary', 'sector': 'PE1', 'decreto': '29'}
        rows = parse_rows(raw, item, 'https://www.mur.gov.it/example.pdf', {'units': []})
        validate(rows, item, None, raw)
        self.assertEqual([(u['unit'], u['role'], u['mur']) for u in rows],
                         [('2026ABCDEF_001', 'PI', 200000), ('2026ABCDEF_002', 'RU', 120000)])
        self.assertEqual(rows[0]['titolo'], 'Un progetto di prova')

    def test_pdf_is_read_and_balanced(self):
        import fitz
        doc = fitz.open()
        page = doc.new_page()
        lines = [
            'PE1 - Tabella B - Progetti finanziati',
            '1 PI VERDI Ada 2026ABCDEF_001 Ateneo Demo 12345678901 100.000,00 200.000,00 300.000,00 200.000,00',
            '2 RU ROSSI Luca 2026ABCDEF_002 Ateneo Due 12345678902 80.000,00 120.000,00 200.000,00 120.000,00',
            'TOTALE COMPLESSIVO 320.000,00',
        ]
        for i, line in enumerate(lines):
            page.insert_text((25, 40 + i * 30), line, fontsize=7)
        rows = parse_annex(doc.tobytes(), {'program':'ordinary','sector':'PE1','decreto':'29'},
                           'https://www.mur.gov.it/example.pdf', None, {'units':[]})
        self.assertEqual([u['mur'] for u in rows], [200000,120000])

    def test_initial_snapshot_has_no_duplicate_or_missing_pi(self):
        data = json.loads((ROOT / 'data' / 'prin.json').read_text(encoding='utf-8'))
        units = data['units']
        identifiers = {(u['program'], u['unit']) for u in units}
        self.assertEqual(len(units), len(identifiers))
        by_program = {p: [u for u in units if u['program'] == p] for p in ('ordinary','hybrid')}
        if data['checkedAt'] is None:
            self.assertEqual((len(by_program['ordinary']),len(by_program['hybrid'])), (726,92))
            self.assertEqual((sum(u['mur'] for u in by_program['ordinary']),sum(u['mur'] for u in by_program['hybrid'])),
                             (155398008,23197367))
        for source in data['sources']:
            matching = [u for u in units if (u['program'],u['sector']) == (source['program'],source['sector'])]
            self.assertEqual(len(matching),source['units'])
            self.assertEqual(sum(u['mur'] for u in matching),source['total'])
        for p in by_program:
            projects = {u['project'] for u in by_program[p]}
            for code in projects:
                self.assertEqual(sum(u['role'] == 'PI' for u in by_program[p] if u['project'] == code), 1, (p,code))


if __name__ == '__main__':
    unittest.main()
