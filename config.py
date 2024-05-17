import os
import configparser
from typing import get_type_hints


class Config:
    def __init__(self):
        self.config_path = os.path.join(os.path.expanduser('~'), '.config', '.dbx_script.cfg')

        types = get_type_hints(self)
        for key in types:
            setattr(self, key, types[key]())

        self.read()

    def read(self):
        config_parser = configparser.ConfigParser(allow_no_value=True)
        config_parser.read(self.config_path)

        for proerty_name in get_type_hints(self):
            value = getattr(self, proerty_name)

            if not config_parser.has_section(proerty_name):
                config_parser.add_section(proerty_name)

            section = config_parser[proerty_name]

            for key in get_type_hints(value):
                setattr(value, key, section.get(key))

    def flush(self):
        config_parser = configparser.ConfigParser(allow_no_value=True)

        for proerty_name in get_type_hints(self):
            value = getattr(self, proerty_name)

            if not config_parser.has_section(proerty_name):
                config_parser.add_section(proerty_name)

            section = config_parser[proerty_name]

            for key in get_type_hints(value):
                section[key] = getattr(value, key)

        with open(self.config_path, 'w') as configfile:
            config_parser.write(configfile)


class AppSection:
    app_key: str
    app_secret: str


class AuthenticationSection:
    access_token: str
    refresh_token: str


class DBXConfig(Config):
    app: AppSection
    auth: AuthenticationSection


config = DBXConfig()
