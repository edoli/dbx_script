import os
import dropbox
import threading
from queue import Queue
from tqdm import tqdm
from retry import retry
import glob
import custom_api
import logging
import traceback


class RepeatTimer(threading.Timer):
    def run(self):
        while not self.finished.wait(self.interval):
            self.function(*self.args, **self.kwargs)


class AccumData:
    def __init__(self):
        self.items = []
        self.total_size = 0


class Item:
    def __init__(self, name, dbx_path, local_path, size):
        self.name = name
        self.dbx_path = dbx_path
        self.local_path = local_path
        self.size = size


def default_entry_filter(entry: dropbox.files.Metadata):
    return True


dbx_cache = {}


def check_dbx_path_exists(dbx: dropbox.Dropbox, dbx_path: str):
    parent_dir = dbx_path[:len(dbx_path) - 1 - dbx_path[::-1].index('/')]

    if not check_dbx_path_exists_in_cache(parent_dir):
        put_dir_to_cache(dbx, parent_dir)

    return check_dbx_path_exists_in_cache(dbx_path)


def check_dbx_path_exists_in_cache(dbx_path: str):
    keys = dbx_path.split('/')

    elem = dbx_cache
    for key in keys:
        if key not in elem:
            return False
        elem = elem[key]

    return True


def put_dir_to_cache(dbx: dropbox.Dropbox, dbx_path: str):
    keys = dbx_path.split('/')

    elem = dbx_cache
    for key in keys:
        if key not in elem:
            elem[key] = {}
        elem = elem[key]

    try:
        entries = dbx.files_list_folder(dbx_path).entries

        for entry in entries:
            name = entry.name
            path = entry.path_lower

            elem[name] = path
    except Exception as e:
        pass


class DBXWorker:

    def __init__(self, dbx: dropbox.Dropbox):
        self.dbx = dbx


    def accumulate_download_files(self, dbx_path, download_dir, accum_data=AccumData(), entry_filter=default_entry_filter):
        """
        Used for download multiple files.
        """
        try:
            entry = self.dbx.files_get_metadata(dbx_path)
            if isinstance(entry, dropbox.files.FileMetadata) and os.path.isdir(download_dir):
                self.process_folder_entries([entry], download_dir, entry_filter, accum_data, join_path=True)
            else:
                self.process_folder_entries([entry], download_dir, entry_filter, accum_data, join_path=False)

        except Exception as e:
            logging.error(traceback.format_exc())
            print(f'Fail to accmulate dbx_path: {dbx_path}, download_dir: {download_dir}')
            
        return accum_data

    def gather_files(self, root_dir: str, rel_dir: str, dbx_dir: str, accum_data: AccumData):
        """
        Used for upload multiple files.
        """
        for fn in os.listdir(root_dir):
            local_path = os.path.join(root_dir, fn)
            rel_path = rel_dir + "/" + fn

            if os.path.isdir(local_path):
                self.gather_files(local_path, rel_path, accum_data)

            else:
                if not filter(local_path):
                    continue

                dbx_path = dbx_dir + rel_path

                if not check_dbx_path_exists(self.dbx, dbx_path):
                    size = os.path.getsize(local_path)

                    accum_data.items.append(Item(rel_path, dbx_path, local_path, size))
                    accum_data.total_size += size

    def glob_files(self, pat: str, rel_dir: str, dbx_dir: str, check_exists: bool, accum_data: AccumData):
        """
        Used for upload multiple files.
        """
        local_paths = glob.glob(pat, recursive=True)

        for local_path in local_paths:
            if os.path.isdir(local_path):
                continue

            rel_path = os.path.relpath(local_path, rel_dir)

            dbx_path = dbx_dir + '/' + rel_path

            if not check_exists or not check_dbx_path_exists(self.dbx, dbx_path):
                size = os.path.getsize(local_path)

                accum_data.items.append(Item(rel_path, dbx_path, local_path, size))
                accum_data.total_size += size

    def process_folder_entries(self, entries, current_dir, entry_filter, accum_data: AccumData, join_path = True):
        if join_path:
            os.makedirs(current_dir, exist_ok=True)

        for entry in sorted(entries, key=lambda x: x.name.lower()):
            name = entry.name
            path = entry.path_lower

            if join_path:
                current_path = os.path.join(current_dir, name)
            else:
                current_path = current_dir

            if not entry_filter(entry):
                continue

            if isinstance(entry, dropbox.files.FileMetadata):
                size = entry.size
                if not os.path.exists(current_path):
                    accum_data.total_size += size
                    accum_data.items.append(Item(name, path, current_path, size))
                else:
                    size_diff = size - os.path.getsize(current_path)
                    if size_diff > 0:
                        accum_data.total_size += size_diff
                        accum_data.items.append(Item(name, path, current_path, size_diff))
            elif isinstance(entry, dropbox.files.FolderMetadata):
                result = self.dbx.files_list_folder(path=path, limit=2000)
                self.process_folder_entries(result.entries, current_path, entry_filter, accum_data)

                while result.has_more:
                    result = self.dbx.files_list_folder_continue(cursor=result.cursor)
                    self.process_folder_entries(result.entries, current_path, entry_filter, accum_data)
            elif isinstance(entry, dropbox.files.DeletedMetadata):
                pass

    def download(self, accum_data, num_worker=1, append=True):
        total_size = accum_data.total_size
        total_size_mb = total_size / 1024 / 1024
        if total_size_mb < 1024:
            print(f'Total size to download: {total_size_mb} MB')
        elif total_size_mb < 1024 * 1024:
            print(f'Total size to download: {total_size_mb / 1024} GB')
        else:
            print(f'Total size to download: {total_size_mb / 1024 / 1024} TB')

        queue = Queue()
        for item in accum_data.items:
            queue.put(item)

        with tqdm(total=accum_data.total_size) as pbar:

            def worker(lock: threading.Lock):
                @retry(tries=4)
                def download(item: Item):
                    local_path = item.local_path
                    dbx_path = item.dbx_path

                    def update_pbar(size):
                        pbar.update(size)

                    cont = True
                    while cont:
                        lock.acquire()
                        try:
                            self.dbx.check_and_refresh_access_token()
                        finally:
                            lock.release()

                        cont = custom_api.files_download_to_file(self.dbx, dbx_path, local_path, append, update_pbar)

                while not queue.empty():
                    item = queue.get()

                    try:
                        download(item)
                    except Exception as e:
                        logging.error(traceback.format_exc())

            lock = threading.Lock()

            if num_worker == 1:
                worker(lock)
            else:
                pools = []

                for i in range(num_worker):
                    t = threading.Thread(target=worker, args=(lock, ))
                    t.start()

                    pools.append(t)

                for pool in pools:
                    pool.join()

    def upload(self, accum_data, num_worker=1):
        pbar = tqdm(total=accum_data.total_size)

        queue = Queue()
        for item in accum_data.items:
            queue.put(item)

        def worker():
            @retry(tries=4)
            def upload(item: Item):
                local_path = item.local_path
                dbx_path = item.dbx_path

                def update_pbar(size):
                    pbar.update(size)

                custom_api.files_upload(self.dbx, dbx_path, local_path, update_pbar)

            while not queue.empty():
                item = queue.get()

                try:
                    upload(item)
                except Exception as e:
                    logging.error(traceback.format_exc())

        if num_worker == 1:
            worker()
        else:
            pools = []

            for i in range(num_worker):
                t = threading.Thread(target=worker)
                t.start()

                pools.append(t)

            for pool in pools:
                pool.join()

    def refresh_access_token(self):
        self.dbx.refresh_access_token()
