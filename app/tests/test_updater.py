import json
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from updater import Updater


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'checkout'
        self.root.mkdir()
        self.git('init', '-b', 'main')
        self.git('config', 'user.name', 'Atlas test')
        self.git('config', 'user.email', 'test@example.invalid')
        (self.root / '.gitignore').write_text('germany-life-hermes/state/\ngermany-life-hermes/data/\n')
        (self.root / 'app').mkdir()
        (self.root / 'app/package.json').write_text(json.dumps({'version': '1.1.0'}))
        self.git('add', '.')
        self.git('commit', '-m', 'old build')
        self.old = self.git('rev-parse', 'HEAD')
        (self.root / 'app/package.json').write_text(json.dumps({'version': '1.2.0'}))
        self.git('add', '.')
        self.git('commit', '-m', 'new build already pulled')
        self.latest = self.git('rev-parse', 'HEAD')
        self.git('remote', 'add', 'origin', 'https://github.com/Vector1239/atlas.git')
        self.git('update-ref', 'refs/remotes/origin/main', self.latest)
        self.bundle = Path(self.temp.name) / 'Applications/Atlas.app'
        self.resources = self.bundle / 'Contents/Resources/app'
        self.resources.mkdir(parents=True)
        (self.resources / 'package.json').write_text(json.dumps({'version': '1.1.0'}))
        (self.resources / 'build-info.json').write_text(json.dumps({'revision': self.old}))
        (self.bundle / 'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': 'local.atlas.assistant'}))
        self.updater = Updater(self.root, self.resources, self.bundle)
        self.fetch = patch.object(self.updater, 'fetch')
        self.fetch.start()
        self.addCleanup(self.fetch.stop)

    def git(self, *args):
        return subprocess.check_output(['/usr/bin/git', *args], cwd=self.root, stderr=subprocess.DEVNULL, text=True).strip()

    def test_already_pulled_source_still_offers_update_for_older_installed_app(self):
        info = self.updater.inspect()
        self.assertEqual(self.git('rev-parse', 'HEAD'), info['latest_revision'])
        self.assertTrue(info['available'])
        self.assertTrue(info['can_install'])
        self.assertEqual(info['latest_version'], '1.2.0')

    def test_matching_build_is_current_even_without_version_bump(self):
        self.updater.revision = self.latest
        self.assertFalse(self.updater.inspect()['available'])

    def test_dirty_checkout_blocks_install_without_touching_local_edits(self):
        manifest = self.root / 'app/package.json'
        manifest.write_text('{"version":"my local edits"}')
        info = self.updater.inspect()
        self.assertFalse(info['can_install'])
        with self.assertRaisesRegex(ValueError, 'Commit or stash'):
            self.updater.install()
        self.assertEqual(manifest.read_text(), '{"version":"my local edits"}')
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.latest)

    def test_unexpected_remote_rejected(self):
        self.git('remote', 'set-url', 'origin', 'https://example.com/another/app.git')
        with self.assertRaisesRegex(ValueError, 'origin'):
            self.updater.inspect()

    def test_build_failure_preserves_installed_app_and_personal_data(self):
        data = self.root / 'germany-life-hermes/data'
        data.mkdir(parents=True)
        (data / 'worklog.csv').write_text('personal shifts stay here')
        before = (self.resources / 'package.json').read_bytes()
        run = self.updater.run
        def fail_build(args, **kwargs):
            if Path(str(args[0])).name == 'npm':
                raise RuntimeError('simulated build failure')
            return run(args, **kwargs)
        with patch.object(self.updater, 'run', side_effect=fail_build):
            with self.assertRaisesRegex(RuntimeError, 'simulated build failure'):
                self.updater.install()
        self.assertEqual((self.resources / 'package.json').read_bytes(), before)
        self.assertEqual((data / 'worklog.csv').read_text(), 'personal shifts stay here')
        self.assertEqual(len(self.git('worktree', 'list', '--porcelain').split('worktree ')) - 1, 1)

    def test_failed_restart_restores_previous_bundle(self):
        staging = self.bundle.parent / 'staging'
        candidate = staging / 'Atlas.app'
        candidate.mkdir(parents=True)
        (candidate / 'new-version').write_text('candidate')
        before = (self.resources / 'package.json').read_bytes()
        with patch.object(self.updater, 'launch_app', return_value=Mock(poll=lambda: 0)) as launch, patch.object(self.updater, 'wait_for_health', side_effect=RuntimeError('not healthy')):
            with self.assertRaisesRegex(RuntimeError, 'not healthy'):
                self.updater.activate(candidate, staging / 'previous.app', {'latest_version': '1.2.0', 'latest_revision': self.latest})
        self.assertEqual((self.resources / 'package.json').read_bytes(), before)
        self.assertEqual(launch.call_count, 2)
        self.assertTrue((staging / 'failed.app/new-version').exists())

    def test_abandoned_update_does_not_leave_controls_busy_forever(self):
        self.updater.status_file.write_text(json.dumps({'phase': 'building', 'worker_pid': 99999999}))
        state = self.updater.status()
        self.assertEqual(state['phase'], 'error')
        self.assertFalse(state['running'])


if __name__ == '__main__':
    unittest.main()
