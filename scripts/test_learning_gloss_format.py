"""Tiny isolated Git/YAML/SQLite fixtures; never reads or changes live glosses.

Run from outside the repository: python -I -X utf8 /absolute/path/to/this.py
The fixture uses all 73 source filenames but only two senses and one pilot row.
Only its pilot-count constant is reduced; production validation still requires
all 3412 immutable pilot IDs. No full dictionary SQLite is built.
"""
from pathlib import Path
from contextlib import closing
import copy
import hashlib
import importlib.util
import json
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import quote

import yaml

HERE = Path(__file__).resolve().parent


def module(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


fmt = module('learning_gloss_format')
checker = module('check_learning_glosses')
builder = module('build_learning_sql')
SID = 'test%1:00:00::'
SYNSET = '00000001-n'


def git(repo, *args, data=None):
    result = subprocess.run(['git', '-C', str(repo), *args], input=data,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return result.stdout.decode('utf8').strip()


def write_yaml(path, value):
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding='utf8')


class FormatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='learning-v2-fixtures-')
        cls.seed = Path(cls.temp.name) / 'seed'
        cls.seed.mkdir()
        base = cls.seed / 'src/yaml'
        base.mkdir(parents=True)
        entries = {'test': {'n': {
            'form': ['tests'], 'sense': [{'id': SID, 'synset': SYNSET},
                                      {'id': 'test%1:00:01::', 'synset': SYNSET}]}}}
        for lemma in ('read/write_memory', 'km/h', 'literal\\backslash'):
            entries[lemma] = {'n': {'sense': [{'id': lemma + '%1:00:00::', 'synset': SYNSET}]}}
        write_yaml(base / 'entries-t.yaml', entries)
        write_yaml(base / 'noun.test.yaml', {SYNSET: {'definition': ['an original definition']}})
        for index in range(71):
            write_yaml(base / ('entries-fixture-%02d.yaml' % index), {})
        for name in fmt.NOTICE_NAMES:
            (cls.seed / name).write_bytes(b'Original license notice.\n')
        git(cls.seed, 'init', '--quiet')
        git(cls.seed, 'add', '--', 'src/yaml', *fmt.NOTICE_NAMES)
        tree = git(cls.seed, 'write-tree')
        # Commit objects only, inside the disposable fixture: no real branch/index
        # is changed and no commit is made in the working repository.
        cls.commit = git(cls.seed, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                         'commit-tree', tree, data=b'Pinned fixture\n')
        git(cls.seed, 'update-ref', 'refs/tags/2025-edition', cls.commit)
        config = {'schema': 'oewn-learning-source-config-v1', 'edition': 'OEWN 2025',
                  'sourceCommit': cls.commit, 'sourceTag': '2025-edition', 'recordSchema': fmt.V2}
        (cls.seed / 'LEARNING_SOURCE.json').write_text(json.dumps(config), encoding='utf8')
        glosses = cls.seed / 'src/learning-glosses'
        glosses.mkdir()
        manifest = {'schema': 'oewn-learning-source-manifest-v1', 'sourceArchiveSha256': fmt.ARCHIVE_PIN,
                    'upstreamCommit': cls.commit, 'glosses': 1,
                    'entries': [{'senseId': SID, 'sha256': 'historical evidence, not a current-row hash'}]}
        (glosses / 'manifest.json').write_text(json.dumps(manifest), encoding='utf8')
        cls.record = {'schema': fmt.V2, 'senseId': SID, 'synsetId': SYNSET,
                      'simpleMeaning': 'a check that something works', 'scope': 'general',
                      'examples': ['The test worked.', 'Try another test.'],
                      'editorialStatus': fmt.EDITORIAL, 'sourceBatch': 1, 'reviewVerdict': 'first-pass'}
        write_yaml(glosses / (quote(SID, safe='') + '.yaml'), cls.record)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory(dir=self.temp.name, prefix='case-')
        self.addCleanup(self.tempdir.cleanup)
        self.repo = Path(self.tempdir.name) / 'repo'
        shutil.copytree(self.seed, self.repo)
        self.path = self.repo / 'src/learning-glosses' / (quote(SID, safe='') + '.yaml')
        for helper in (fmt, checker.fmt, builder.fmt):
            self.enterContext(patch.object(helper, 'PILOT_GLOSSES', 1))

    def config(self, **changes):
        path = self.repo / 'LEARNING_SOURCE.json'
        value = json.loads(path.read_bytes())
        value.update(changes)
        path.write_text(json.dumps(value), encoding='utf8')

    def test_v2_exact_fields_no_hashes(self):
        self.assertEqual(set(self.record), fmt.V2_FIELDS)
        with patch.object(hashlib, 'sha256', side_effect=AssertionError('v2 must not hash')):
            result = checker.check(self.repo)
        self.assertEqual(result['sourceCommit'], self.commit)
        self.assertEqual(result['recordSchema'], fmt.V2)
        self.assertEqual(result['sourceFiles'], 73)
        self.assertEqual(result['learningGlosses'], 1)
        self.assertEqual(result['status'], 'ok')
        self.assertFalse(any('sha' in key.casefold() for key in result))

    def commit_learning_fixture(self):
        git(self.repo, 'add', '--', 'LEARNING_SOURCE.json', 'src/learning-glosses')
        tree = git(self.repo, 'write-tree')
        commit = git(self.repo, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                     'commit-tree', tree, '-p', self.commit, data=b'Learning fixture\n')
        git(self.repo, 'update-ref', 'HEAD', commit)
        return commit

    def test_sql_layout_and_runtime_queries_without_hashing(self):
        learning_commit = self.commit_learning_fixture()
        out = Path(self.tempdir.name) / 'tiny.sqlite'
        with patch.object(hashlib, 'sha256', side_effect=AssertionError('v2 must not hash')):
            result = builder.build(self.repo, out)
        with closing(sqlite3.connect(out)) as db:
            overlay = db.execute('SELECT * FROM overlays').fetchone()
            self.assertEqual(overlay, (SID, self.record['simpleMeaning'], 'general',
                                       builder.encode(self.record['examples']), ''))
            self.assertEqual([x[1] for x in db.execute('PRAGMA table_info(overlays)')],
                             ['sense_id', 'simple_meaning', 'scope', 'examples_json', 'source_sha256'])
            self.assertEqual(db.execute('SELECT count(*) FROM notices WHERE sha256 = ? ', ('',)).fetchone()[0], 2)
            metadata = dict(db.execute('SELECT * FROM metadata'))
            self.assertEqual(metadata['sourceCommit'], self.commit)
            self.assertEqual(metadata['learningCommit'], learning_commit)
            self.assertEqual(result['learningCommit'], learning_commit)
            self.assertEqual(metadata['learningWorkingTree'], 'clean')
            self.assertEqual(metadata['recordSchema'], fmt.V2)
            self.assertFalse(any('sha' in key.casefold() for key in metadata))
            rows = db.execute('''SELECT s.sense_id,s.original_meaning,o.simple_meaning
                                 FROM form_senses f JOIN senses s USING(sense_id)
                                 LEFT JOIN overlays o USING(sense_id) WHERE f.form=?''', ('tests',)).fetchall()
            self.assertEqual(len(rows), 2)
            self.assertEqual(sum(row[2] is not None for row in rows), 1)
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertFalse(any('sha' in key.casefold() for key in result))

    def test_malformed_schema_and_fields(self):
        variants = [dict(self.record, schema='unknown'),
                    dict(self.record, sourceDefinitionSha256='0' * 64),
                    {key: value for key, value in self.record.items() if key != 'scope'},
                    dict(self.record, schema=fmt.V1)]
        for row in variants:
            with self.subTest(row=row):
                write_yaml(self.path, row)
                with self.assertRaisesRegex(ValueError, 'schema/fields'):
                    checker.check(self.repo)

    def test_malformed_content(self):
        for field, value in [('simpleMeaning', ''), ('scope', ' '), ('reviewVerdict', None),
                             ('sourceBatch', True), ('sourceBatch', 0),
                             ('editorialStatus', 'draft'), ('examples', ['same', 'same']),
                             ('examples', ['one', {}]), ('examples', ['one', ' '])]:
            with self.subTest(field=field, value=value):
                write_yaml(self.path, dict(self.record, **{field: value}))
                with self.assertRaises(ValueError):
                    checker.check(self.repo)

    def test_exact_identity_and_path(self):
        for change in ({'synsetId': 'wrong'}, {'senseId': 'foreign'}, {'senseId': '../bad'}):
            write_yaml(self.path, dict(self.record, **change))
            with self.assertRaises(ValueError):
                checker.check(self.repo)
        write_yaml(self.path, self.record)
        self.path.rename(self.path.with_name('wrong.yaml'))
        with self.assertRaisesRegex(ValueError, 'identity/path'):
            checker.check(self.repo)

    def test_encoded_source_separator_ids_accepted_by_checker_and_sql(self):
        ids = [lemma + '%1:00:00::' for lemma in
               ('read/write_memory', 'km/h', 'literal\\backslash')]
        for sid in ids:
            path = self.path.parent / (quote(sid, safe='') + '.yaml')
            write_yaml(path, dict(self.record, senseId=sid))
            self.assertNotIn('/', path.name)
            self.assertNotIn('\\', path.name)
        self.commit_learning_fixture()
        with patch.object(hashlib, 'sha256', side_effect=AssertionError('v2 must not hash')):
            self.assertEqual(checker.check(self.repo)['learningGlosses'], 4)
            out = Path(self.tempdir.name) / 'separator-ids.sqlite'
            self.assertEqual(builder.build(self.repo, out)['learningGlosses'], 4)
        with closing(sqlite3.connect(out)) as db:
            actual = {row[0] for row in db.execute('SELECT sense_id FROM overlays')}
        self.assertEqual(actual, {SID, *ids})

    def test_separator_ids_reject_raw_mismatched_unknown_and_nul_paths(self):
        config, paths, _ = fmt.verify_source(self.repo)
        synsets, _, senses = fmt.source_index(paths)
        for sid in ('read/write_memory%1:00:00::', 'literal\\backslash%1:00:00::'):
            row = dict(self.record, senseId=sid)
            for path in (self.path.parent / (sid + '.yaml'),
                         self.path.parent / 'incorrect.yaml'):
                with self.subTest(sid=sid, path=path), self.assertRaisesRegex(ValueError, 'identity/path'):
                    fmt.validate_record(row, path, senses, synsets, config['recordSchema'])
        for sid in ('unknown/slash%1:00:00::', 'unknown\\backslash%1:00:00::', 'bad\x00id'):
            row = dict(self.record, senseId=sid)
            path = self.path.parent / (quote(sid, safe='') + '.yaml')
            with self.subTest(sid=sid), self.assertRaises(ValueError):
                fmt.validate_record(row, path, senses, synsets, config['recordSchema'])

    def test_duplicate_yaml_key(self):
        self.path.write_text(self.path.read_text(encoding='utf8') + 'scope: duplicate\n', encoding='utf8')
        with self.assertRaisesRegex(ValueError, 'Duplicate YAML key'):
            checker.check(self.repo)

    def test_source_definition_mapping_forms_and_notices_drift(self):
        mutations = [('src/yaml/noun.test.yaml', b'definition', b'changed'),
                     ('src/yaml/entries-t.yaml', SYNSET.encode(), b'99999999-n'),
                     ('src/yaml/entries-t.yaml', b'tests', b'other-form'),
                     ('LICENSE.md', b'Original', b'Altered'),
                     ('WNDB_License.txt', b'Original', b'Altered')]
        for name, old, new in mutations:
            path = self.repo / name
            original = path.read_bytes()
            path.write_bytes(original.replace(old, new))
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'content differs'):
                checker.check(self.repo)
            path.write_bytes(original)

    def test_source_inventory_add_remove_and_rename(self):
        path = self.repo / 'src/yaml/entries-fixture-00.yaml'
        original = path.read_bytes()
        added = path.with_name('extra.yaml')
        added.write_bytes(b'{}\n')
        with self.assertRaisesRegex(ValueError, 'inventory'):
            checker.check(self.repo)
        added.unlink()
        path.unlink()
        with self.assertRaisesRegex(ValueError, 'inventory'):
            checker.check(self.repo)
        added.write_bytes(original)  # Same count as pinned source still fails.
        with self.assertRaisesRegex(ValueError, 'inventory'):
            checker.check(self.repo)

    def test_missing_license_rejected(self):
        (self.repo / 'WNDB_License.txt').unlink()
        with self.assertRaisesRegex(ValueError, 'Unsafe input'):
            checker.check(self.repo)

    def test_source_crlf_is_only_allowed_normalization(self):
        for path in [*(self.repo / 'src/yaml').glob('*.yaml'),
                     *(self.repo / name for name in fmt.NOTICE_NAMES)]:
            path.write_bytes(path.read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))
        self.assertTrue(checker.check(self.repo)['sourceSnapshotVerified'])
        path = self.repo / 'LICENSE.md'
        path.write_bytes(path.read_bytes() + b' ')
        with self.assertRaisesRegex(ValueError, 'content differs'):
            checker.check(self.repo)

    def test_missing_invalid_or_unavailable_source_config(self):
        path = self.repo / 'LEARNING_SOURCE.json'
        original = path.read_bytes()
        path.unlink()
        with self.assertRaises((OSError, ValueError)):
            checker.check(self.repo)
        path.write_bytes(original)
        for commit in ('HEAD', '--help', 'f' * 40, '0' * 39, None):
            self.config(sourceCommit=commit)
            with self.subTest(commit=commit), self.assertRaises(ValueError):
                checker.check(self.repo)
        self.config(sourceCommit=self.commit, recordSchema='unknown')
        with self.assertRaisesRegex(ValueError, 'configuration'):
            checker.check(self.repo)

    def test_tag_must_resolve_to_pinned_commit(self):
        self.config(sourceTag='missing')
        with self.assertRaises(ValueError):
            checker.check(self.repo)
        tree = git(self.repo, 'rev-parse', self.commit + '^{tree}')
        other = git(self.repo, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                    'commit-tree', tree, data=b'Other commit\n')
        git(self.repo, 'update-ref', 'refs/tags/2025-edition', other)
        self.config(sourceTag='2025-edition')
        with self.assertRaisesRegex(ValueError, 'sourceTag does not resolve'):
            checker.check(self.repo)

    def test_commit_must_be_commit_not_blob(self):
        blob = git(self.repo, 'rev-parse', self.commit + ':LICENSE.md')
        self.config(sourceCommit=blob)
        with self.assertRaisesRegex(ValueError, 'commit object'):
            checker.check(self.repo)

    def test_missing_pilot_record_rejected_by_checker_and_builder(self):
        self.path.unlink()
        self.commit_learning_fixture()
        with self.assertRaisesRegex(ValueError, 'Previously imported gloss missing'):
            checker.check(self.repo)
        out = Path(self.tempdir.name) / 'missing.sqlite'
        with self.assertRaisesRegex(ValueError, 'Previously imported gloss missing'):
            builder.build(self.repo, out)
        self.assertFalse(out.exists())

    def test_historical_pilot_hashes_not_current_record_hashes(self):
        row = copy.deepcopy(self.record)
        row['simpleMeaning'] = 'a revised learner meaning'
        write_yaml(self.path, row)
        self.assertEqual(checker.check(self.repo)['learningGlosses'], 1)

    def test_manifest_count_and_membership_are_still_enforced(self):
        path = self.repo / 'src/learning-glosses/manifest.json'
        manifest = json.loads(path.read_bytes())
        manifest['entries'].append(manifest['entries'][0])
        path.write_text(json.dumps(manifest), encoding='utf8')
        with self.assertRaisesRegex(ValueError, 'manifest differs'):
            checker.check(self.repo)
        # Outside the tiny fixture override, the real guard is 3412, not 1.
        with patch.object(checker.fmt, 'PILOT_GLOSSES', 3412):
            with self.assertRaisesRegex(ValueError, 'manifest differs'):
                checker.check(self.repo)

    def test_legacy_v1_explicit_configuration_and_definition_check(self):
        self.config(recordSchema=fmt.V1)
        row = dict(self.record, schema=fmt.V1, sourceArchiveSha256=fmt.ARCHIVE_PIN,
                   sourceDefinitionSha256=hashlib.sha256(b'an original definition').hexdigest(),
                   sourceFinalSha256='a' * 64)
        write_yaml(self.path, row)
        self.assertEqual(checker.check(self.repo)['recordSchema'], fmt.V1)
        out = Path(self.tempdir.name) / 'legacy.sqlite'
        self.commit_learning_fixture()
        self.assertEqual(builder.build(self.repo, out)['learningGlosses'], 1)
        row['sourceDefinitionSha256'] = '0' * 64
        write_yaml(self.path, row)
        with self.assertRaisesRegex(ValueError, 'Legacy gloss source evidence differs'):
            checker.check(self.repo)

    def test_sql_source_drift_rejected_before_output(self):
        (self.repo / 'LICENSE.md').write_bytes(b'changed\n')
        out = Path(self.tempdir.name) / 'drift.sqlite'
        with self.assertRaisesRegex(ValueError, 'content differs'):
            builder.build(self.repo, out)
        self.assertFalse(out.exists())

    def test_sql_requires_clean_committed_learning_version(self):
        out = Path(self.tempdir.name) / 'dirty.sqlite'
        with self.assertRaises(ValueError):
            builder.build(self.repo, out)
        first = self.commit_learning_fixture()
        write_yaml(self.path, dict(self.record, scope='A changed scope.'))
        with self.assertRaisesRegex(ValueError, 'Commit dictionary'):
            builder.build(self.repo, out)
        second = self.commit_learning_fixture()
        self.assertNotEqual(first, second)
        result = builder.build(self.repo, out)
        self.assertEqual(result['learningCommit'], second)
        self.assertEqual(result['learningWorkingTree'], 'clean')

    def test_release_ignores_generated_bytecode_but_not_tools(self):
        scripts = self.repo / 'scripts'
        scripts.mkdir()
        (scripts / 'tool.py').write_text('print(1)\n')
        (self.repo / '.gitignore').write_text('__pycache__/\n*.pyc\n')
        git(self.repo, 'add', '--', 'scripts', '.gitignore')
        commit = self.commit_learning_fixture()
        cache = scripts / '__pycache__'
        cache.mkdir()
        (cache / 'helper.pyc').write_bytes(b'generated')
        self.assertEqual(builder.learning_version(self.repo), commit)
        (scripts / 'tool.py').write_text('print(2)\n')
        with self.assertRaisesRegex(ValueError, 'Commit dictionary'):
            builder.learning_version(self.repo)

    def test_isolated_cli_entrypoints(self):
        self.commit_learning_fixture()
        out = Path(self.tempdir.name) / 'cli.sqlite'
        report = out.with_suffix('.json')
        # Exercise command-line imports under -I. The tiny manifest is rejected,
        # proving both scripts load their sibling helper and production guards.
        import sys
        for name, args in [('check_learning_glosses', []),
                           ('build_learning_sql', ['--out', str(out), '--report', str(report)])]:
            result = subprocess.run([sys.executable, '-I', '-X', 'utf8', str(HERE / (name + '.py')),
                                     '--repo', str(self.repo), *args],
                                    cwd=self.tempdir.name, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'Initial migration manifest differs', result.stderr)
        self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
