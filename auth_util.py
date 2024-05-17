import dropbox
from config import config
from dropbox import DropboxOAuth2FlowNoRedirect


def run_cli_procedure():
    if config.app.app_key is None or config.app.app_secret is None:
        get_app_key_secret()

    if config.auth.refresh_token is None:
        get_refresh_token()

    while not validate_auth():
        print('Current REFRESH_TOKEN is not valid')
        get_refresh_token()
    
    print("Now have valid TOKEN")


def get_dbx_client():
    dbx = dropbox.Dropbox(
        app_key=config.app.app_key,
        app_secret=config.app.app_secret,
        oauth2_refresh_token=config.auth.refresh_token)
    return dbx


def get_app_key_secret():
    app_key = input("Enter the APP_KEY here: ").strip()
    app_secret = input("Enter the APP_SECRET here: ").strip()

    config.app.app_key = app_key
    config.app.app_secret = app_secret
    config.flush()


def get_refresh_token():
    refresh_token = input("Enter the REFRESH_TOKEN here (leave blank if you want to create new token): ").strip()

    if refresh_token != '':
        config.auth.refresh_token = refresh_token
        config.flush()
        return

    app_key = config.app.app_key
    app_secret = config.app.app_secret

    auth_flow = DropboxOAuth2FlowNoRedirect(app_key, app_secret, token_access_type='offline')

    authorize_url = auth_flow.start()
    print("1. Go to: " + authorize_url)
    print("2. Click \"Allow\" (you might have to log in first).")
    print("3. Copy the authorization code.")
    auth_code = input("Enter the authorization code here: ").strip()

    try:
        oauth_result = auth_flow.finish(auth_code)
    except Exception as e:
        print('Error: %s' % (e,))
        exit(1)

    print('access_token: ', oauth_result.access_token)
    print('refresh_token: ', oauth_result.refresh_token)
    with dropbox.Dropbox(oauth2_access_token=oauth_result.access_token) as dbx:
        dbx.users_get_current_account()
        print("Successfully set up client!")

    config.auth.access_token = oauth_result.access_token
    config.auth.refresh_token = oauth_result.refresh_token
    config.flush()


def validate_auth():
    dbx = dropbox.Dropbox(
        app_key=config.app.app_key,
        app_secret=config.app.app_secret,
        oauth2_refresh_token=config.auth.refresh_token)

    user = None
    try:
        user = dbx.users_get_current_account()
    except Exception as e:
        pass

    return user is not None
