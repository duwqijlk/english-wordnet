"""Build a read-only SQLite index from centrally pinned OEWN and reviewed YAML.

Run from outside the checkout using Python -I. Git commits/PRs are provenance;
no record, inventory, report or SQLite digests are generated. The v1 SQL table
layout is retained for readers (including SELECT *): overlays.source_sha256 and
notices.sha256 are deprecated, empty compatibility columns, not proof fields.
"""
from pathlib import Path
import argparse
import importlib.util
import json
import os
import sqlite3
import tempfile

_spec = importlib.util.spec_from_file_location('learning_gloss_format',
                                             Path(__file__).with_name('learning_gloss_format.py'))
fmt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fmt)


def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def norm(value):
    return value.replace('­', '').replace('’', "'").casefold()


def build(repo, out):
    repo = Path(repo).resolve()
    out = Path(out)
    if out.exists() or out.is_symlink() or not out.parent.is_dir():
        raise FileExistsError('Output exists or parent missing')
    config, paths, notices = fmt.verify_source(repo)
    synsets, entries, source_senses = fmt.source_index(paths)
    records = fmt.learning_records(repo / 'src/learning-glosses', source_senses, synsets, config['recordSchema'])
    senses, forms = {}, {}
    for sid, (synset, lemma, lexical_key) in source_senses.items():
        entry = entries[lemma][lexical_key]
        declared = entry.get('form', [])
        if not isinstance(declared, list):
            raise ValueError('Invalid forms')
        definitions = synsets[synset]['definition']
        senses[sid] = (sid, lemma, lexical_key, lexical_key[0], synset,
                       '; '.join(definitions), encode(definitions))
        for spelling in [lemma, *declared]:
            if not isinstance(spelling, str) or not spelling.strip():
                raise ValueError('Invalid form')
            forms.setdefault((norm(spelling), sid), set()).add('exact' if spelling == lemma else 'declared')
    overlays = [(sid, row['simpleMeaning'], row['scope'], encode(row['examples']), '')
                for sid, row in sorted(records.items())]
    metadata = [('schema', 'oewn-yaml-query-v1'), ('sourceCommit', config['sourceCommit']),
                ('recordSchema', config['recordSchema']), ('edition', config['edition']),
                ('sourceSnapshotVerified', 'true'), ('studentValidated', 'false')]
    if config.get('sourceTag'):
        metadata.append(('sourceTag', config['sourceTag']))
    fd, temp = tempfile.mkstemp(prefix='.yaml-dictionary-', suffix='.tmp', dir=out.parent)
    os.close(fd)
    try:
        db = sqlite3.connect(temp)
        try:
            db.execute('PRAGMA page_size=4096')
            db.execute('PRAGMA journal_mode=DELETE')
            db.execute('PRAGMA foreign_keys=ON')
            db.executescript('''
              CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
              CREATE TABLE notices(name TEXT PRIMARY KEY,text TEXT NOT NULL,sha256 TEXT NOT NULL);
              CREATE TABLE senses(sense_id TEXT PRIMARY KEY,lemma TEXT NOT NULL,lexical_key TEXT NOT NULL,pos TEXT NOT NULL,synset_id TEXT NOT NULL,original_meaning TEXT NOT NULL,definitions_json TEXT NOT NULL);
              CREATE TABLE form_senses(form TEXT NOT NULL,sense_id TEXT NOT NULL REFERENCES senses(sense_id),origins_json TEXT NOT NULL,PRIMARY KEY(form,sense_id));
              CREATE INDEX form_senses_by_sense ON form_senses(sense_id);
              CREATE TABLE overlays(sense_id TEXT PRIMARY KEY REFERENCES senses(sense_id),simple_meaning TEXT NOT NULL,scope TEXT NOT NULL,examples_json TEXT NOT NULL,source_sha256 TEXT NOT NULL);
            ''')
            db.execute('BEGIN IMMEDIATE')
            db.executemany('INSERT INTO metadata VALUES (?,?)', metadata)
            db.executemany('INSERT INTO notices VALUES (?,?,?)', notices)
            db.executemany('INSERT INTO senses VALUES (?,?,?,?,?,?,?)', sorted(senses.values()))
            db.executemany('INSERT INTO form_senses VALUES (?,?,?)',
                           [(form, sid, encode(sorted(origins))) for (form, sid), origins in sorted(forms.items())])
            db.executemany('INSERT INTO overlays VALUES (?,?,?,?,?)', overlays)
            db.commit()
            if (db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok'
                    or db.execute('PRAGMA foreign_key_check').fetchall()):
                raise ValueError('SQLite integrity/foreign key check failed')
        finally:
            db.close()
        os.link(temp, out)
    finally:
        Path(temp).unlink(missing_ok=True)
    return {'sourceCommit': config['sourceCommit'], 'recordSchema': config['recordSchema'],
            'sourceFiles': len(paths), 'synsets': len(synsets), 'lemmas': len(entries),
            'senses': len(senses), 'formLinks': len(forms), 'learningGlosses': len(overlays),
            'sqliteBytes': out.stat().st_size, 'sourceSnapshotVerified': True, 'status': 'ok',
            'studentValidated': False, 'remotePublished': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists() or args.report.resolve() == args.out.resolve():
        raise FileExistsError('Report exists or equals SQL output')
    result = build(args.repo, args.out)
    with args.report.open('x', encoding='utf8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
