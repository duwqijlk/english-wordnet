"""Build a versioned, read-only SQLite index from ONE OEWN-derived YAML tree.

Run from the project root with Python -I; do not run Python from inside an
untrusted downloaded tree. Source YAML is data and loaded with safe_load only;
this reviewed build script executes after the OEWN-derived repository is trusted.
No server or remote publication. The original 2025 tag is used as a checked starting point,
not as a permanently frozen build input.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import sqlite3
import tempfile
from urllib.parse import quote
import yaml

PIN='7d749f6e2c39e6970e4997839dcf6e42fd281f3c2fae0171d2192bae8cfa4b51'


def digest(raw):return hashlib.sha256(raw).hexdigest()
def encode(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'))
def norm(value):return value.replace('­','').replace('’',"'").casefold()


def load_yaml(path,limit=12*1024*1024):
    if path.is_symlink() or not path.is_file() or path.stat().st_size>limit:raise ValueError('Unsafe YAML member: '+str(path))
    value=yaml.safe_load(path.read_bytes())
    if not isinstance(value,dict):raise ValueError('Expected YAML mapping: '+str(path))
    return value


def build(repo,out):
    repo=Path(repo).resolve();out=Path(out)
    if out.exists() or out.is_symlink() or not out.parent.is_dir():raise FileExistsError('Output exists or parent missing')
    base=repo/'src/yaml';glosses=repo/'src/learning-glosses'
    if not base.is_dir() or not glosses.is_dir():raise ValueError('OEWN source and learning gloss folders required')
    paths=sorted(base.glob('*.yaml'))
    if len(paths)!=73:raise ValueError('Expected 73 source YAML members; inspect source version before building')
    source_hash=digest(encode([(p.name,digest(p.read_bytes())) for p in paths]).encode())
    synsets={};entries={}
    for path in paths:
        data=load_yaml(path)
        if path.name.startswith('entries-'):
            for lemma,groups in data.items():
                if lemma in entries or not isinstance(groups,dict):raise ValueError('Duplicate/invalid lemma')
                entries[lemma]=groups
        elif path.name!='frames.yaml':
            for ident,row in data.items():
                if ident in synsets or not isinstance(row,dict) or not row.get('definition'):
                    raise ValueError('Duplicate/invalid synset')
                synsets[ident]=row
    senses={};forms={}
    for lemma,groups in entries.items():
        for lexical_key,entry in groups.items():
            if not isinstance(entry,dict):raise ValueError('Invalid lexical group')
            spellings=[lemma,*entry.get('form',[])]
            for sense in entry.get('sense',[]):
                sid=sense['id'];synset=sense['synset']
                if sid in senses or synset not in synsets:raise ValueError('Duplicate/unknown sense or synset')
                definitions=synsets[synset]['definition']
                meaning='; '.join(definitions)
                senses[sid]=(sid,lemma,lexical_key,lexical_key[0],synset,meaning,encode(definitions))
                for spelling in spellings:
                    if not isinstance(spelling,str) or not spelling.strip():raise ValueError('Invalid form')
                    forms.setdefault((norm(spelling),sid),set()).add('exact' if spelling==lemma else 'declared')
    manifest_path=glosses/'manifest.json';manifest=json.loads(manifest_path.read_bytes())
    if manifest.get('schema')!='oewn-learning-source-manifest-v1' or manifest.get('sourceArchiveSha256')!=PIN:
        raise ValueError('Invalid original migration manifest')
    # The manifest is retained as migration evidence, not a daily edit index.
    # A new or edited sense needs exactly one YAML file; build discovers files
    # and binds the release to their current hashes after editorial PR review.
    overlays={};overlay_sources=[]
    for path in sorted(glosses.glob('*.yaml')):
        if path.is_symlink() or path.parent.resolve()!=glosses.resolve():raise ValueError('Foreign gloss path')
        raw=path.read_bytes();value=load_yaml(path)
        if set(value)!={'schema','senseId','synsetId','sourceArchiveSha256','sourceDefinitionSha256',
                'simpleMeaning','scope','examples','editorialStatus','sourceBatch','sourceFinalSha256','reviewVerdict'}:
            raise ValueError('Unexpected gloss fields')
        sid=value['senseId']
        if not isinstance(sid,str) or not sid or len(sid)>250 or '..' in sid or any(ch in sid for ch in ('/','\\','\x00')):
            raise ValueError('Unsafe gloss sense ID')
        if path.name!=quote(sid,safe='')+'.yaml' or value['schema']!='oewn-learning-gloss-v1' or value['sourceArchiveSha256']!=PIN:
            raise ValueError('Gloss identity/path/archive differs')
        if sid in overlays or sid not in senses or value['synsetId']!=senses[sid][4]:
            raise ValueError('Invalid gloss sense identity')
        if value['sourceDefinitionSha256']!=digest(senses[sid][5].encode('utf8')):
            raise ValueError('Gloss original definition changed; editorial re-review required')
        if value['editorialStatus']!='reviewed-model-not-student-validated':raise ValueError('Unreviewed gloss')
        text=value['simpleMeaning'];examples=value['examples']
        if (not isinstance(text,str) or not text.strip() or not isinstance(value['scope'],str) or not value['scope'].strip()
                or not isinstance(examples,list) or len(examples)<2 or len({x for x in examples if isinstance(x,str)})!=len(examples)
                or any(not isinstance(x,str) or not x.strip() for x in examples)):
            raise ValueError('Invalid gloss content')
        file_hash=digest(raw)
        overlays[sid]=(sid,text,value['scope'],encode(examples),file_hash)
        overlay_sources.append((sid,file_hash))
    if not overlays:raise ValueError('No reviewed learning glosses')
    known={row['senseId'] for row in manifest.get('entries',[])}
    if not known<=set(overlays):raise ValueError('Initial reviewed gloss silently deleted; explicit removal workflow required')
    overlay_hash=digest(encode(overlay_sources).encode('utf8'))
    notice=[]
    for name,expected in [('LICENSE.md','672cc8b5663e8dc74c4b07a9dcf477193853575b119908fd3dc0aeeb60a9dbbb'),
                          ('WNDB_License.txt','df30ec18fbabcdaf031b79ea026d3e6b959010cffe6dd7be9ac137822175b904')]:
        raw=(repo/name).read_bytes()
        canonical=raw.replace(b'\r\n',b'\n')
        if digest(canonical)!=expected:raise ValueError('Original license notice changed; review license update')
        notice.append((name,canonical.decode('utf8'),expected))
    fd,temp=tempfile.mkstemp(prefix='.yaml-dictionary-',suffix='.tmp',dir=out.parent);os.close(fd)
    try:
        db=sqlite3.connect(temp)
        try:
            db.execute('PRAGMA page_size=4096');db.execute('PRAGMA journal_mode=DELETE');db.execute('PRAGMA foreign_keys=ON')
            db.executescript('''
              CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
              CREATE TABLE notices(name TEXT PRIMARY KEY,text TEXT NOT NULL,sha256 TEXT NOT NULL);
              CREATE TABLE senses(sense_id TEXT PRIMARY KEY,lemma TEXT NOT NULL,lexical_key TEXT NOT NULL,pos TEXT NOT NULL,synset_id TEXT NOT NULL,original_meaning TEXT NOT NULL,definitions_json TEXT NOT NULL);
              CREATE TABLE form_senses(form TEXT NOT NULL,sense_id TEXT NOT NULL REFERENCES senses(sense_id),origins_json TEXT NOT NULL,PRIMARY KEY(form,sense_id));
              CREATE INDEX form_senses_by_sense ON form_senses(sense_id);
              CREATE TABLE overlays(sense_id TEXT PRIMARY KEY REFERENCES senses(sense_id),simple_meaning TEXT NOT NULL,scope TEXT NOT NULL,examples_json TEXT NOT NULL,source_sha256 TEXT NOT NULL);
            ''')
            db.execute('BEGIN IMMEDIATE')
            db.executemany('INSERT INTO metadata VALUES (?,?)',[
                ('schema','oewn-yaml-query-v1'),('sourceYamlSha256',source_hash),
                ('glossSourceSha256',overlay_hash),
                ('migrationManifestSha256',digest(manifest_path.read_bytes())),
                ('originalEditionArchiveSha256',PIN),('upstreamBaseCommit',manifest['upstreamCommit']),
                ('studentValidated','false')])
            db.executemany('INSERT INTO notices VALUES (?,?,?)',notice)
            db.executemany('INSERT INTO senses VALUES (?,?,?,?,?,?,?)',sorted(senses.values()))
            db.executemany('INSERT INTO form_senses VALUES (?,?,?)',[(form,sid,encode(sorted(origins))) for (form,sid),origins in sorted(forms.items())])
            db.executemany('INSERT INTO overlays VALUES (?,?,?,?,?)',sorted(overlays.values()))
            db.commit()
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or db.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('SQLite integrity/foreign key check failed')
        finally:db.close()
        os.link(temp,out)
    finally:Path(temp).unlink(missing_ok=True)
    return {'sourceYamlSha256':source_hash,'synsets':len(synsets),'lemmas':len(entries),
            'senses':len(senses),'formLinks':len(forms),'learningGlosses':len(overlays),
            'sqliteBytes':out.stat().st_size,'sqliteSha256':digest(out.read_bytes()),
            'studentValidated':False,'remotePublished':False}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--repo',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True);parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    if args.report.exists() or args.report==args.out:raise FileExistsError('Report exists or equals SQL output')
    result=build(args.repo,args.out)
    with args.report.open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print({k:v for k,v in result.items() if k!='sourceYamlSha256'})


if __name__=='__main__':main()
