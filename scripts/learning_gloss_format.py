"""Shared learning-gloss validation; Git objects, not row hashes, pin v2 source.

This module is loaded by explicit path by the trusted command-line scripts so
that they also work under Python -I, without importing from the current folder.
"""
from pathlib import Path
import json
import os
import re
import subprocess
from urllib.parse import quote

import yaml

V1 = 'oewn-learning-gloss-v1'
V2 = 'oewn-learning-gloss-v2'
EDITORIAL = 'reviewed-model-not-student-validated'
ARCHIVE_PIN = '7d749f6e2c39e6970e4997839dcf6e42fd281f3c2fae0171d2192bae8cfa4b51'
PILOT_GLOSSES = 3412
SOURCE_FILES = 73
NOTICE_NAMES = ('LICENSE.md', 'WNDB_License.txt')
V2_FIELDS = frozenset(('schema', 'senseId', 'synsetId', 'simpleMeaning', 'scope',
                       'examples', 'editorialStatus', 'sourceBatch', 'reviewVerdict'))
V1_FIELDS = V2_FIELDS | {'sourceArchiveSha256', 'sourceDefinitionSha256', 'sourceFinalSha256'}


class UniqueLoader(yaml.SafeLoader):
    """Do not silently accept duplicate record/source keys."""


def _mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if key in result:
            raise ValueError('Duplicate YAML key: ' + str(key))
        result[key] = loader.construct_object(value_node, deep=True)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def read_bytes(path, limit=12 * 1024 * 1024):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError('Unsafe input: ' + str(path))
    return path.read_bytes()


def load_yaml(path):
    value = yaml.load(read_bytes(path), Loader=UniqueLoader)
    if not isinstance(value, dict):
        raise ValueError('Expected YAML mapping: ' + str(path))
    return value


def git_env():
    # A partial clone must fail for absent objects, never fetch them implicitly.
    return {**os.environ, 'GIT_NO_LAZY_FETCH': '1', 'GIT_TERMINAL_PROMPT': '0'}


def git(repo, *args):
    result = subprocess.run(['git', '--no-replace-objects', '-C', str(repo), *args],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=git_env())
    if result.returncode:
        raise ValueError('Cannot verify local Git source: ' + result.stderr.decode('utf8', 'replace').strip())
    return result.stdout


def source_config(repo):
    config = json.loads(read_bytes(Path(repo) / 'LEARNING_SOURCE.json'))
    if (not isinstance(config, dict)
            or config.get('schema') != 'oewn-learning-source-config-v1'
            or config.get('edition') != 'OEWN 2025'
            or config.get('recordSchema') not in (V1, V2)
            or not isinstance(config.get('sourceCommit'), str)
            or re.fullmatch(r'[0-9a-f]{40}', config['sourceCommit']) is None):
        raise ValueError('Invalid LEARNING_SOURCE.json source configuration')
    commit = config['sourceCommit']
    if git(repo, 'cat-file', '-t', commit).strip() != b'commit':
        raise ValueError('sourceCommit must name a local commit object')
    if 'sourceTag' in config:
        tag = config['sourceTag']
        if not isinstance(tag, str) or not tag or '\x00' in tag:
            raise ValueError('Invalid sourceTag')
        git(repo, 'check-ref-format', 'refs/tags/' + tag)
        resolved = git(repo, 'rev-parse', '--verify', 'refs/tags/' + tag + '^{commit}').decode().strip()
        if resolved != commit:
            raise ValueError('sourceTag does not resolve to sourceCommit')
    return config


def verify_source(repo):
    """Compare every source/notice byte to local pinned blobs; allow CRLF only.

    The complete Git tree inventory is compared to the working tree, including
    untracked files. Reading all blobs in one cat-file process avoids 75 process
    launches, and does not depend on filters, the index, HEAD or the network.
    """
    repo = Path(repo).resolve()
    config = source_config(repo)
    base = repo / 'src/yaml'
    if (base.is_symlink() or (repo / 'src').is_symlink() or not base.is_dir()):
        raise ValueError('Unsafe/missing source YAML directory')
    tree = git(repo, 'ls-tree', '-rz', config['sourceCommit'], '--', 'src/yaml', *NOTICE_NAMES)
    blobs = {}
    for item in tree.split(b'\x00'):
        if not item:
            continue
        header, name = item.split(b'\t', 1)
        mode, kind, oid = header.split()
        name = name.decode('utf8')
        if kind != b'blob' or mode not in (b'100644', b'100755'):
            raise ValueError('Non-regular pinned source member: ' + name)
        blobs[name] = oid
    expected = {name for name in blobs if name.startswith('src/yaml/')}
    if (len(expected) != SOURCE_FILES
            or any(Path(name).parent.as_posix() != 'src/yaml' or not name.endswith('.yaml') for name in expected)
            or set(blobs) != expected | set(NOTICE_NAMES)):
        raise ValueError('Expected 73 source YAML members and both license notices in sourceCommit')
    actual = set()
    for path in base.rglob('*'):
        if path.is_symlink():
            raise ValueError('Unsafe source path: ' + str(path))
        if path.is_file():
            actual.add(path.relative_to(repo).as_posix())
    if actual != expected:
        raise ValueError('Source file inventory differs from sourceCommit')
    # Object IDs here are Git's existing coordinates, never newly computed hashes.
    raw = subprocess.run(['git', '--no-replace-objects', '-C', str(repo), 'cat-file', '--batch'],
                         input=b''.join(oid + b'\n' for oid in blobs.values()),
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=git_env())
    if raw.returncode:
        raise ValueError('Cannot read pinned Git source blobs')
    offset = 0
    notices = []
    for name, oid in blobs.items():
        end = raw.stdout.find(b'\n', offset)
        header = raw.stdout[offset:end].split()
        if len(header) != 3 or header[0] != oid or header[1] != b'blob':
            raise ValueError('Missing/invalid pinned Git source blob: ' + name)
        size = int(header[2])
        start = end + 1
        original = raw.stdout[start:start + size]
        offset = start + size + 1
        current = read_bytes(repo / name)
        if current.replace(b'\r\n', b'\n') != original.replace(b'\r\n', b'\n'):
            raise ValueError('Source content differs from sourceCommit: ' + name)
        if name in NOTICE_NAMES:
            notices.append((name, current.replace(b'\r\n', b'\n').decode('utf8'), ''))
    return config, [repo / name for name in sorted(expected)], sorted(notices)


def source_index(paths):
    synsets, entries = {}, {}
    for path in paths:
        data = load_yaml(path)
        if path.name.startswith('entries-'):
            for lemma, groups in data.items():
                if lemma in entries or not isinstance(lemma, str) or not isinstance(groups, dict):
                    raise ValueError('Duplicate/invalid lemma')
                entries[lemma] = groups
        elif path.name != 'frames.yaml':
            for ident, row in data.items():
                if (ident in synsets or not isinstance(row, dict)
                        or not isinstance(row.get('definition'), list) or not row['definition']
                        or any(not isinstance(x, str) or not x.strip() for x in row['definition'])):
                    raise ValueError('Duplicate/invalid synset')
                synsets[ident] = row
    senses = {}
    for lemma, groups in entries.items():
        for lexical_key, entry in groups.items():
            if not isinstance(lexical_key, str) or not lexical_key or not isinstance(entry, dict):
                raise ValueError('Invalid lexical group')
            for sense in entry.get('sense', []):
                sid, synset = sense['id'], sense['synset']
                if not isinstance(sid, str) or sid in senses or synset not in synsets:
                    raise ValueError('Duplicate/unknown sense or synset')
                senses[sid] = (synset, lemma, lexical_key)
    return synsets, entries, senses


def pilot_ids(glosses):
    """Historical manifest proves membership only, never current YAML hashes."""
    manifest = json.loads(read_bytes(Path(glosses) / 'manifest.json'))
    if (not isinstance(manifest, dict) or manifest.get('schema') != 'oewn-learning-source-manifest-v1'
            or manifest.get('sourceArchiveSha256') != ARCHIVE_PIN
            or manifest.get('glosses') != PILOT_GLOSSES
            or not isinstance(manifest.get('entries'), list)
            or len(manifest['entries']) != PILOT_GLOSSES):
        raise ValueError('Initial migration manifest differs')
    ids = [row.get('senseId') if isinstance(row, dict) else None for row in manifest['entries']]
    if any(not isinstance(sid, str) or not sid for sid in ids) or len(set(ids)) != PILOT_GLOSSES:
        raise ValueError('Invalid/duplicate initial migration sense IDs')
    return set(ids)


def validate_record(row, path, senses, synsets, record_schema):
    schema = row.get('schema')
    fields = V2_FIELDS if schema == V2 else V1_FIELDS if schema == V1 else None
    if fields is None or schema != record_schema or set(row) != fields:
        raise ValueError('Unexpected gloss schema/fields: ' + str(path))
    sid = row['senseId']
    # OEWN IDs legitimately contain separators (read/write_memory, km/h).
    # They are data, not paths: the exact encoded basename and pinned-source
    # membership below are the boundary, including for a literal backslash.
    if (not isinstance(sid, str) or not sid or len(sid) > 250 or '..' in sid
            or '\x00' in sid):
        raise ValueError('Unsafe gloss sense ID')
    if path.name != quote(sid, safe='') + '.yaml' or sid not in senses or row['synsetId'] != senses[sid][0]:
        raise ValueError('Original sense identity/path differs: ' + sid)
    if row['editorialStatus'] != EDITORIAL:
        raise ValueError('Unreviewed gloss: ' + sid)
    for field in ('simpleMeaning', 'scope', 'reviewVerdict'):
        if not isinstance(row[field], str) or not row[field].strip():
            raise ValueError('Invalid gloss ' + field + ': ' + sid)
    if type(row['sourceBatch']) is not int or row['sourceBatch'] < 1:
        raise ValueError('Invalid gloss sourceBatch: ' + sid)
    examples = row['examples']
    if (not isinstance(examples, list) or len(examples) < 2
            or any(not isinstance(x, str) or not x.strip() for x in examples)
            or len(set(examples)) != len(examples)):
        raise ValueError('Missing, blank or duplicate examples: ' + sid)
    if schema == V1:
        # Compatibility for archived v1 rows only. v2 never imports hashlib.
        import hashlib
        definition = '; '.join(synsets[senses[sid][0]]['definition'])
        if (row['sourceArchiveSha256'] != ARCHIVE_PIN
                or row['sourceDefinitionSha256'] != hashlib.sha256(definition.encode('utf8')).hexdigest()
                or not isinstance(row['sourceFinalSha256'], str)
                or re.fullmatch(r'[0-9a-f]{64}', row['sourceFinalSha256']) is None):
            raise ValueError('Legacy gloss source evidence differs: ' + sid)
    return sid


def learning_records(glosses, senses, synsets, record_schema):
    glosses = Path(glosses)
    if glosses.is_symlink() or not glosses.is_dir():
        raise ValueError('Unsafe/missing learning gloss directory')
    known = pilot_ids(glosses)
    records = {}
    for path in sorted(glosses.glob('*.yaml')):
        row = load_yaml(path)
        sid = validate_record(row, path, senses, synsets, record_schema)
        if sid in records:
            raise ValueError('Duplicate sense gloss: ' + sid)
        records[sid] = row
    if not known <= records.keys():
        raise ValueError('Previously imported gloss missing')
    if not records:
        raise ValueError('No reviewed learning glosses')
    return records
