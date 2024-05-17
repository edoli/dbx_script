import dbx_util
import auth_util
import dropbox

def main():
    dbx = auth_util.get_dbx_client()

    worker = dbx_util.DBXWorker(dbx)

    accum_data = worker.accumulate_download_files('', '')

    worker.download(accum_data, num_worker=8)


if __name__ == '__main__':
    main()