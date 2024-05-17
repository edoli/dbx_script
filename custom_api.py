import requests
import os
import dropbox
import time


DOWNLOAD_URL = 'https://content.dropboxapi.com/2/files/download'


def files_download_to_file(dbx: dropbox.Dropbox, dbx_path: str, local_path: str, append: bool, on_update=None):
    # Check parameter
    if type(append) != bool:
        raise ValueError("append parameter is not bool")

    dbx.check_and_refresh_access_token()

    start = 0
    if os.path.exists(local_path):
        if append:
            start = os.path.getsize(local_path)
        else:
            os.remove(local_path)

    headers = {
        'Authorization': f'Bearer {dbx._oauth2_access_token}',
        'Dropbox-API-Arg': f'{{"path": "{dbx_path}"}}',
        'Range': f'bytes={start}-',
        }

    with requests.get(DOWNLOAD_URL, headers=headers, stream=True) as r:
        if r.reason != 'Range Not Satisfiable':
            r.raise_for_status()

            if os.path.exists(local_path):
                with open(local_path, 'ab') as f:
                    return iter_download(r, f, on_update)
            else:
                with open(local_path, 'wb') as f:
                    return iter_download(r, f, on_update)

    return False


def iter_download(response, f, on_update):
    start_time = time.time()

    for chunk in response.iter_content(chunk_size=2**16):
        f.write(chunk)
        if on_update is not None:
            on_update(len(chunk))

        if (time.time() - start_time) > 60 * 60:
            return True

    return False


CHUNK_SIZE = 4 * 1024 * 1024


def files_upload(dbx: dropbox.Dropbox, dbx_path: str, local_path: str, on_update=None):
    dbx.check_and_refresh_access_token()

    file_size = os.path.getsize(local_path)

    with open(local_path, 'rb') as f:

        if file_size > CHUNK_SIZE:
            result = dbx.files_upload_session_start(f.read(CHUNK_SIZE))
            cursor = dropbox.files.UploadSessionCursor(session_id=result.session_id, offset=f.tell())
            commit = dropbox.files.CommitInfo(path=dbx_path)

            if on_update is not None:
                on_update(CHUNK_SIZE)

            while f.tell() <= file_size:
                if ((file_size - f.tell()) <= CHUNK_SIZE):
                    dbx.files_upload_session_finish(f.read(CHUNK_SIZE), cursor, commit)
                    if on_update is not None:
                        on_update(CHUNK_SIZE)
                    break
                else:
                    dbx.files_upload_session_append_v2(f.read(CHUNK_SIZE), cursor)
                    cursor.offset = f.tell()

                    if on_update is not None:
                        on_update(CHUNK_SIZE)

        else:
            result = dbx.files_upload(f.read(), dbx_path, dropbox.files.WriteMode.overwrite)

            if on_update is not None:
                on_update(file_size)
