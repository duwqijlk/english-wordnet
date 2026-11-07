"""Validate every learning gloss against the original YAML before PR review.

Run from outside an untrusted checkout using Python -I; only YAML safe_load is
used. No database, browser, network or write side effects.
"""
from pathlib import Path
import argparse
import hashlib
import json
from urllib.parse import quote
import yaml

PIN='7d749f6e2c39e6970e4997839dcf6e42fd281f3c2fae0171d2192bae8cfa4b51'


def digest(raw):return hashlib.sha256(raw).hexdigest()


def load(path):
    if path.is_symlink() or path.stat().st_size>12*1024*1024:raise ValueError('Unsafe input: '+str(path))
    value=yaml.safe_load(path.read_bytes())
    if not isinstance(value,dict):raise ValueError('Expected YAML mapping: '+str(path))
    return value


def check(repo):
    root=Path(repo).resolve();base=root/'src/yaml';glosses=root/'src/learning-glosses'
    synsets={};senses={};files=sorted(base.glob('*.yaml'))
    if len(files)!=73:raise ValueError('Unexpected OEWN source version')
    for path in files:
        data=load(path)
        if path.name.startswith('entries-'):
            for lemma,groups in data.items():
                for pos,entry in groups.items():
                    for row in entry.get('sense',[]):
                        sid=row['id']
                        if sid in senses:raise ValueError('Duplicate source sense')
                        senses[sid]=(row['synset'],lemma,pos)
        elif path.name!='frames.yaml':
            for ident,synset in data.items():
                if ident in synsets:raise ValueError('Duplicate synset')
                synsets[ident]='; '.join(synset['definition'])
    baseline=json.loads((glosses/'manifest.json').read_bytes())
    if baseline.get('sourceArchiveSha256')!=PIN or baseline.get('glosses')!=3412:
        raise ValueError('Initial migration manifest differs')
    seen=set();names=[]
    for path in sorted(glosses.glob('*.yaml')):
        row=load(path);sid=row['senseId']
        if sid in seen or sid not in senses or path.name!=quote(sid,safe='')+'.yaml':raise ValueError('Foreign/duplicate sense gloss')
        seen.add(sid)
        expected=senses[sid]
        if row.get('schema')!='oewn-learning-gloss-v1' or row.get('sourceArchiveSha256')!=PIN or row.get('synsetId')!=expected[0]:
            raise ValueError('Original sense identity differs: '+sid)
        if row.get('sourceDefinitionSha256')!=digest(synsets[expected[0]].encode('utf8')):
            raise ValueError('Original definition changed: '+sid)
        if row.get('editorialStatus')!='reviewed-model-not-student-validated':raise ValueError('Unreviewed gloss')
        if not isinstance(row.get('simpleMeaning'),str) or not row['simpleMeaning'].strip():raise ValueError('Blank learning gloss')
        examples=row.get('examples')
        if not isinstance(examples,list) or len(examples)<2 or len({x for x in examples if isinstance(x,str)})!=len(examples):
            raise ValueError('Missing or duplicate examples')
        names.append((sid,digest(path.read_bytes())))
    old={x['senseId'] for x in baseline['entries']}
    if not old<=seen:raise ValueError('Previously imported gloss missing')
    return {'sourceSenses':len(senses),'learningGlosses':len(seen),
        'glossSourceSha256':digest(json.dumps(names,sort_keys=True,separators=(',',':')).encode('utf8')),
        'sourceSnapshotVerified':True,'semanticAcceptance':False,'studentValidated':False}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--repo',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(check(args.repo),ensure_ascii=False))


if __name__=='__main__':main()
