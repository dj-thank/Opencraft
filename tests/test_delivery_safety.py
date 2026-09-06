"""Source delivery and one-client setup must not leak or silently skip checks."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout, redirect_stderr
import importlib.util
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from opencraft_server.auth import TokenAuthority
from opencraft_server.database import Database
from opencraft_server.workspace import LocalWorkspace

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


setup = load_script('setup_client')
builder = load_script('build_release')
gate = load_script('run_quality_gate')
checker = load_script('check_repo')


class DeliverySafetyTests(unittest.TestCase):
    def test_setup_touches_only_selected_client(self):
        for selected in ('codex', 'claude'):
            with self.subTest(client=selected), tempfile.TemporaryDirectory() as directory:
                def which(name):
                    self.assertEqual(name, selected)
                    return '/native/' + name
                with patch.object(setup, 'ROOT', Path(directory)), patch.object(setup.shutil, 'which', side_effect=which), \
                     patch.object(setup.subprocess, 'run') as run, redirect_stdout(io.StringIO()):
                    self.assertEqual(setup.main([selected]), 0)
                commands = [item.args[0] for item in run.call_args_list]
                self.assertEqual(commands[-1][0], '/native/' + selected)
                self.assertIn('opencraft_server.mcp', commands[-1])
                self.assertIn(selected, commands[-1])
                self.assertFalse(any('shell' in item.kwargs for item in run.call_args_list))

    def test_setup_dry_run_and_missing_selected_client_do_not_mutate(self):
        for selected in ('codex', 'claude'):
            with patch.object(setup.shutil, 'which', return_value=None), patch.object(setup.subprocess, 'run') as run, \
                 redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(setup.main([selected, '--dry-run']), 0)
                self.assertEqual(setup.main([selected]), 2)
                run.assert_not_called()

    def test_paths_with_spaces_remain_individual_arguments(self):
        python = Path('/private path/python')
        data = Path('/private path/world')
        command = setup.registration_command('claude', 'claude', python, data)
        self.assertIn(str(python), command)
        self.assertIn(str(data), command)
        with self.assertRaises(ValueError):
            setup.registration_command('other', 'other', python, data)

    def test_missing_npm_blocks_release_gate(self):
        with patch.object(gate.shutil, 'which', return_value=None):
            result = gate.run('js', ['npm', 'test'], required_program='npm')
        self.assertTrue(result.blocking)
        self.assertNotEqual(result.status, 'passed')

    def test_private_world_and_authentication_are_never_packaged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = ['README.md', 'src/good.py', 'docs/guide.md', 'src/token-pepper.bin',
                     'src/bootstrap-token.txt', 'src/.env.local', 'src/owner-session.txt',
                     'src/world.sqlite3-wal', 'src/world.sqlite3-shm', 'src/world.sqlite3',
                     '.opencraft-data/token-pepper.bin', 'other-world/private.txt', '.venv/credentials.json']
            for name in paths:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text('fixture')
            with patch.object(builder, 'ROOT', root):
                actual = {f.relative_to(root).as_posix() for f in builder.source_files()}
            self.assertEqual(actual, {'README.md', 'src/good.py', 'docs/guide.md'})

    @unittest.skipIf(os.name == 'nt', 'creating symlinks requires a Windows privilege')
    def test_source_symlinks_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'src').mkdir()
            (root / 'private').write_text('fixture')
            (root / 'src' / 'leak.txt').symlink_to(root / 'private')
            with patch.object(builder, 'ROOT', root), self.assertRaises(RuntimeError):
                builder.source_files()

    def test_secret_scanner_never_prints_matched_material(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            secret = 'sk-' + 'Z' * 32
            (root / 'sample.txt').write_text(secret)
            output = io.StringIO()
            with patch.object(checker, 'ROOT', root), redirect_stderr(output):
                self.assertEqual(checker.main(), 1)
            self.assertNotIn(secret, output.getvalue())
            self.assertNotIn('sample.txt', output.getvalue())

    def test_concurrent_authority_initialization_publishes_one_complete_key(self):
        with tempfile.TemporaryDirectory() as directory:
            with ThreadPoolExecutor(max_workers=8) as pool:
                authorities = list(pool.map(lambda _: TokenAuthority.from_data_directory(directory), range(8)))
            fingerprints = {authority.token_hash('synthetic-test-value') for authority in authorities}
            self.assertEqual(len(fingerprints), 1)
            self.assertEqual(len((Path(directory) / 'token-pepper.bin').read_bytes()), 32)
            self.assertEqual(list(Path(directory).glob('.pepper-*')), [])

    def test_cancelled_database_transaction_rolls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / 'world.sqlite3')
            with self.assertRaises(KeyboardInterrupt), database.transaction(immediate=True) as connection:
                connection.execute("INSERT INTO metadata VALUES('interrupted','value')")
                raise KeyboardInterrupt()
            with database.transaction() as connection:
                self.assertIsNone(connection.execute("SELECT value FROM metadata WHERE key='interrupted'").fetchone())
