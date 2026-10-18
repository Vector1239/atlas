"""Install the pinned local model; verify bytes before making it available to Atlas."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

MODEL = json.loads((Path(__file__).parent / 'content/local-model.json').read_text())


def verify(path, spec=None):
    spec = spec or MODEL
    if path.stat().st_size != spec['size']:
        raise ValueError('The model download is incomplete (unexpected file size).')
    digest = hashlib.sha256()
    with path.open('rb') as source:
        while chunk := source.read(8 * 1024 * 1024):
            digest.update(chunk)
    if digest.hexdigest() != spec['sha256']:
        raise ValueError('The model checksum does not match its published SHA-256. Do not use this file.')


def install(folder, verify_only=False):
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / MODEL['filename']
    partial = target.with_suffix(target.suffix + '.part')
    ready = target.with_suffix('.ready')
    if target.exists():
        try:
            verify(target)
        except ValueError:
            ready.unlink(missing_ok=True)
            raise
    else:
        complete = False
        if partial.exists() and partial.stat().st_size >= MODEL['size']:
            # Resuming past the end gets HTTP 416, so check a finished download first.
            try:
                verify(partial)
                complete = True
            except ValueError:
                partial.unlink()  # a corrupt full-size file would fail the same way on every resume
                if verify_only:
                    raise
        if not complete:
            if not verify_only:
                offset = partial.stat().st_size if partial.exists() else 0
                url = f"https://huggingface.co/{MODEL['repository']}/resolve/{MODEL['revision']}/{MODEL['source_filename']}?download=true"
                headers = {'User-Agent': 'Atlas model installer (+https://github.com/Vector1239/atlas)'}
                if offset:
                    headers['Range'] = f'bytes={offset}-'
                with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
                    resumed = response.status == 206 and response.headers.get('Content-Range', '').startswith(f'bytes {offset}-')
                    if response.status == 206 and not resumed:
                        raise ValueError('The model server returned an unexpected resume position.')
                    with partial.open('ab' if resumed else 'wb') as output:
                        while chunk := response.read(8 * 1024 * 1024):
                            output.write(chunk)
            try:
                verify(partial)
            except ValueError:
                if partial.exists() and partial.stat().st_size >= MODEL['size']:
                    partial.unlink()
                raise
        partial.replace(target)
    ready.write_text(MODEL['sha256'] + '\n')
    print(f"{MODEL['name']} verified and installed ({MODEL['size']/1e9:.2f} GB).")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder', type=Path, default=Path.home() / '.cache/Atlas/models')
    parser.add_argument('--verify-only', action='store_true', help='Verify an existing model or completed .part download without downloading.')
    args = parser.parse_args()
    install(args.folder, args.verify_only)
