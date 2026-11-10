"""Validate learning glosses and centrally pinned OEWN source before PR review.

Run from outside the checkout using Python -I. Only safe YAML data and local Git
objects are read; no database, browser, network or write side effects.
"""
from pathlib import Path
import argparse
import importlib.util
import json

# Explicit trusted sibling import works even when Python -I omits sys.path[0].
_spec = importlib.util.spec_from_file_location('learning_gloss_format',
                                             Path(__file__).with_name('learning_gloss_format.py'))
fmt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fmt)


def check(repo):
    root = Path(repo).resolve()
    config, paths, _notices = fmt.verify_source(root)
    synsets, _entries, senses = fmt.source_index(paths)
    records = fmt.learning_records(root / 'src/learning-glosses', senses, synsets, config['recordSchema'])
    return {'sourceCommit': config['sourceCommit'], 'recordSchema': config['recordSchema'],
            'sourceFiles': len(paths), 'sourceSenses': len(senses), 'learningGlosses': len(records),
            'sourceSnapshotVerified': True, 'status': 'ok',
            'semanticAcceptance': False, 'studentValidated': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.repo), ensure_ascii=False))


if __name__ == '__main__':
    main()
