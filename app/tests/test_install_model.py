import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import install_model


class ModelInstallTests(unittest.TestCase):
    def test_verified_partial_is_promoted_and_ready_only_after_checksum_matches(self):
        body = b'verified-model-bytes'
        spec = {'filename':'test.gguf', 'name':'Test model', 'size':len(body), 'sha256':hashlib.sha256(body).hexdigest()}
        with tempfile.TemporaryDirectory() as folder, patch.object(install_model, 'MODEL', spec):
            root = Path(folder)
            (root/'test.gguf.part').write_bytes(body)
            install_model.install(root, verify_only=True)
            self.assertEqual((root/'test.gguf').read_bytes(), body)
            self.assertEqual((root/'test.ready').read_text().strip(), spec['sha256'])
            self.assertFalse((root/'test.gguf.part').exists())

    def test_same_size_corrupt_model_is_rejected_and_stale_ready_marker_removed(self):
        spec = {'filename':'test.gguf', 'name':'Test model', 'size':4, 'sha256':hashlib.sha256(b'good').hexdigest()}
        with tempfile.TemporaryDirectory() as folder, patch.object(install_model, 'MODEL', spec):
            root = Path(folder)
            (root/'test.gguf').write_bytes(b'bad!')
            (root/'test.ready').write_text('stale')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                install_model.install(root, verify_only=True)
            self.assertFalse((root/'test.ready').exists())

    def test_incomplete_download_never_becomes_ready(self):
        spec = {'filename':'test.gguf', 'size':100, 'sha256':'0'*64}
        with tempfile.TemporaryDirectory() as folder, patch.object(install_model, 'MODEL', spec):
            root = Path(folder)
            (root/'test.gguf.part').write_bytes(b'partial')
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                install_model.install(root, verify_only=True)
            self.assertFalse((root/'test.ready').exists())
            self.assertFalse((root/'test.gguf').exists())


if __name__ == '__main__':
    unittest.main()
