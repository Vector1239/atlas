#!/opt/homebrew/bin/python3.12
"""One-time recovery for an installed Atlas whose old updater blocks local edits."""
import fcntl
import os
from pathlib import Path
import sys

from updater import Updater, alive, read_json


def main():
    root = Path(__file__).resolve().parent.parent
    bundle = Path.home() / 'Applications/Atlas.app'
    if not bundle.exists():
        bundle = Path('/Applications/Atlas.app')
    resources = bundle / 'Contents/Resources/app'
    if not (resources / 'package.json').is_file():
        raise ValueError('The installed Atlas app could not be found in Applications.')
    updater = Updater(root, resources, bundle)
    runtime = read_json(updater.state_dir / 'atlas_runtime.json', {})
    if alive(runtime.get('pid')):
        raise ValueError('Quit Atlas with Command-Q, then open this recovery updater again.')
    with (updater.state_dir / 'atlas-update.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another Atlas update is already running.')
        print('Preparing Atlas from GitHub main. Build progress is saved in the update log.',flush=True)
        with updater.log_file.open('a') as log:
            saved = [os.dup(1),os.dup(2)]
            try:
                os.dup2(log.fileno(),1)
                os.dup2(log.fileno(),2)
                updater.install()
            finally:
                sys.stdout.flush()
                sys.stderr.flush()
                os.dup2(saved[0],1)
                os.dup2(saved[1],2)
                for descriptor in saved:
                    os.close(descriptor)
    print('Atlas update finished. Your local source work has been preserved.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'Atlas could not update: {error}', file=sys.stderr)
        sys.exit(1)
