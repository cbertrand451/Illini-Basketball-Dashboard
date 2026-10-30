"""Stage a full data refresh and retain a recoverable snapshot when publishing."""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import shutil
import tempfile
from typing import Optional


@dataclass
class BuildWorkspace:
    processed: Path
    images: Path
    backup: Optional[Path] = None


def _files(processed, images):
    files = {}
    if processed.exists():
        for path in processed.rglob('*'):
            if path.is_file() and not path.name.endswith('.bak'):
                files[('processed', path.relative_to(processed))] = path
    gallery = images / 'action_photos.json'
    if gallery.exists():
        files[('images', Path('action_photos.json'))] = gallery
    return files


def _fingerprints(files):
    return {key: hashlib.sha256(path.read_bytes()).digest() for key, path in files.items()}


def _replace_file(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
            temporary = Path(handle.name)
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _publish(workspace, live_processed, baseline):
    live_images = live_processed.parent / 'images'
    current = _files(live_processed, live_images)
    if _fingerprints(current) != baseline:
        raise RuntimeError('Saved data changed while the build was running; refusing to overwrite it')
    staged = _files(workspace.processed, workspace.images)
    if current.keys() - staged.keys():
        raise ValueError('The staged build removed saved files; refusing to publish')
    changed = {key: path for key, path in staged.items()
               if key not in baseline or hashlib.sha256(path.read_bytes()).digest() != baseline[key]}
    if not changed:
        return

    backups = live_processed.parent / '.build-backups'
    backups.mkdir(exist_ok=True)
    workspace.backup = Path(tempfile.mkdtemp(prefix='full-build-', dir=backups))
    # Snapshot all previous outputs, not just the last individual file written.
    for (group, relative), path in current.items():
        destination = workspace.backup / group / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
    applied = []
    try:
        for key, source in changed.items():
            group, relative = key
            target = (live_processed if group == 'processed' else live_images) / relative
            applied.append((key, target))
            _replace_file(source, target)
    except BaseException as failure:
        # Network/parse failures never reach here. Restore earlier replacements
        # if a normal write failure or Ctrl+C interrupts the publish step.
        try:
            for key, target in reversed(applied):
                group, relative = key
                if key in baseline:
                    _replace_file(workspace.backup / group / relative, target)
                else:
                    target.unlink(missing_ok=True)
        except BaseException as rollback_failure:
            raise RuntimeError(
                f'Could not finish rollback. Recover the previous data from {workspace.backup}'
            ) from rollback_failure
        failure.add_note(f'Previous files restored. Recovery snapshot: {workspace.backup}')
        raise


@contextmanager
def staged_build(processed_dir):
    """Keep live outputs unchanged during scraping and roll back failed writes.

    Backup directories remain available after publication. A hard process kill or
    power loss during publication may require recovery from that snapshot.
    """
    processed = Path(processed_dir).resolve()
    data_root = processed.parent
    data_root.mkdir(parents=True, exist_ok=True)
    lock = data_root / '.full-data-build.lock'
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError(
            f'Another full build may be running ({lock}). If a previous process '
            'was killed, confirm it has stopped before removing this lock.'
        ) from exc
    os.close(descriptor)
    try:
        live_images = data_root / 'images'
        original = _files(processed, live_images)
        baseline = _fingerprints(original)
        with tempfile.TemporaryDirectory(prefix='.full-build-', dir=data_root) as temporary:
            workspace = BuildWorkspace(Path(temporary) / 'processed', Path(temporary) / 'images')
            for (group, relative), path in original.items():
                destination = (workspace.processed if group == 'processed' else workspace.images) / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)
            workspace.processed.mkdir(exist_ok=True)
            workspace.images.mkdir(exist_ok=True)
            yield workspace
            _publish(workspace, processed, baseline)
    finally:
        lock.unlink(missing_ok=True)
