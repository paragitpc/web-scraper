from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

import dropbox
from dropbox.exceptions import ApiError, AuthError
from dropbox.files import WriteMode


CHUNK_SIZE = 8 * 1024 * 1024


def get_client() -> dropbox.Dropbox:
    refresh_token = os.environ.get("DROPBOX_REFRESH_TOKEN")
    app_key = os.environ.get("DROPBOX_APP_KEY")
    app_secret = os.environ.get("DROPBOX_APP_SECRET")
    access_token = os.environ.get("DROPBOX_ACCESS_TOKEN")

    if refresh_token and app_key and app_secret:
        return dropbox.Dropbox(
            oauth2_refresh_token=refresh_token,
            app_key=app_key,
            app_secret=app_secret,
        )
    if access_token:
        return dropbox.Dropbox(access_token)
    raise RuntimeError(
        "Missing Dropbox credentials. Set DROPBOX_REFRESH_TOKEN+DROPBOX_APP_KEY+DROPBOX_APP_SECRET "
        "or DROPBOX_ACCESS_TOKEN."
    )


def upload_file(
    dbx: dropbox.Dropbox,
    local_path: str | Path,
    remote_path: str,
    overwrite: bool = True,
) -> dict:
    local_path = Path(local_path)
    size = local_path.stat().st_size
    mode = WriteMode("overwrite") if overwrite else WriteMode("add")

    with local_path.open("rb") as fh:
        if size <= CHUNK_SIZE:
            res = dbx.files_upload(fh.read(), remote_path, mode=mode, mute=True)
            return {"name": res.name, "size": res.size, "rev": res.rev}

        session = dbx.files_upload_session_start(fh.read(CHUNK_SIZE))
        cursor = dropbox.files.UploadSessionCursor(
            session_id=session.session_id, offset=fh.tell()
        )
        commit = dropbox.files.CommitInfo(path=remote_path, mode=mode, mute=True)

        while fh.tell() < size:
            chunk = fh.read(CHUNK_SIZE)
            if (size - fh.tell()) <= 0:
                res = dbx.files_upload_session_finish(chunk, cursor, commit)
                return {"name": res.name, "size": res.size, "rev": res.rev}
            dbx.files_upload_session_append_v2(chunk, cursor)
            cursor.offset = fh.tell()

        res = dbx.files_upload_session_finish(b"", cursor, commit)
        return {"name": res.name, "size": res.size, "rev": res.rev}


def walk_files(local_root: str | Path) -> Iterator[Path]:
    root = Path(local_root)
    for p in root.rglob("*"):
        if p.is_file():
            yield p


def upload_tree(
    local_root: str | Path,
    remote_root: str,
    overwrite: bool = True,
    verbose: bool = True,
) -> dict[str, int]:
    dbx = get_client()
    try:
        dbx.users_get_current_account()
    except AuthError as e:
        raise RuntimeError(f"Dropbox auth failed: {e}") from e

    root = Path(local_root).resolve()
    remote_root = remote_root.rstrip("/")
    stats = {"uploaded": 0, "errors": 0, "bytes": 0}

    for f in walk_files(root):
        rel = f.relative_to(root).as_posix()
        target = f"{remote_root}/{rel}"
        try:
            res = upload_file(dbx, f, target, overwrite=overwrite)
            stats["uploaded"] += 1
            stats["bytes"] += res["size"]
            if verbose:
                print(f"  [up] {rel}  ({res['size']:,} bytes)")
        except ApiError as e:
            stats["errors"] += 1
            print(f"  [err] {rel}: {e}")
    return stats
