from . import settings
from logging import getLogger
log = getLogger(__name__)

from os import listdir, path, makedirs
import re


class BitcoindConf:
    """
    Wrapper around a bitcoind configuration file
    """
    conf_line = re.compile('\s*([a-z]*)\s*=\s*(.*)')

    @classmethod
    def list_conf_files(cls):
        return (f for f in listdir(settings.BITCOIN_CONF_DIR) if path.isfile(path.join(settings.BITCOIN_CONF_DIR, f)))

    @classmethod
    def from_file(cls, filename):
        full_path = path.join(settings.BITCOIN_CONF_DIR, filename)
        if not path.exists(full_path):
            log.error("Conf: {} does not exist".format(full_path))

        conf = {}
        with open(full_path, 'r') as f:
            for line in f.readlines():
                match = cls.conf_line.match(line)
                if match is None:
                    continue

                conf[match.group(1)] = match.group(2)

        return cls(filename, conf)

    @classmethod
    def enumerate_confs(cls):
        return (cls.from_file(fn) for fn in cls.list_conf_files())

    @classmethod
    def get_conf(cls, filename):
        return

    def __init__(self, filename, conf):
        self.filename = filename
        self.conf = conf

    def path(self):
        return path.join(settings.BITCOIN_CONF_DIR, self.filename)

    def datadir(self):
        dd = path.join(settings.BITCOIN_DATA_DIR, self.filename)
        makedirs(dd, mode=0o700, exist_ok=True)
        return dd
