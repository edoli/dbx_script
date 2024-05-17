import dropbox
import os
from dbx_util import *
import custom_api
import auth_util
import os


def main():
    dbx = auth_util.get_dbx_client()

    home_path = os.path.expanduser('~')

    worker = DBXWorker(dbx)

    accum_data = AccumData()
    
    worker.glob_files(f'', f'', '', accum_data)

    worker.upload(accum_data, num_worker=8)


if __name__ == '__main__':
    main()
