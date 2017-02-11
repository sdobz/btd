from . import settings
from . import int2bit

from bitcoin.rpc import Proxy, InWarmupError
from bitcoin.core import b2lx, lx
from http.client import CannotSendRequest, BadStatusLine
from gevent import sleep

import os
from os import listdir, path, makedirs
import subprocess
import re

from logging import getLogger
log = getLogger(__name__)


def load_confs():
    confs = {}
    for conf in BitcoindConf.enumerate_confs():
        log.info("Found conf:{}".format(conf.filename))
        confs[conf.filename] = conf

    return confs


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


def start_bitcoind(conf: BitcoindConf):
    log.info("Starting: {}".format(conf.filename))
    # Create conf
    # Check conf
    # Check ports
    # Write conf
    # Connect to rpc
    rpc = connect_rpc(conf)
    try:
        log.info("Testing RPC connection: http://{}:{}".format(conf.conf['rpcbind'], conf.conf['rpcport']))
        rpc.get_info()
    except ConnectionRefusedError:
        log.info("Connection failed, starting bitcoind...")
        subprocess.Popen(['bitcoind', '-conf={}'.format(conf.path()), "-datadir={}".format(conf.datadir())], preexec_fn=os.setsid)
        while True:
            try:
                rpc.get_info()
                break
            except ConnectionRefusedError:
                log.info("Retrying...")
                sleep(1)

    log.info("Connection successful, bitcoind:{} is running".format(conf.filename))


conn = {}


def connect_rpc(conf: BitcoindConf):
    """
    :rtype: BitcoindRPC
    """
    global conn
    if conf.filename not in conn:
        conn[conf.filename] = BitcoindRPC(conf)
    return conn[conf.filename]


def try_robustly(f):
    def attempt(self, *args, **kwargs):
        try:
            try:
                return f(self, *args, **kwargs)
            except (CannotSendRequest, BadStatusLine):
                # Handle reconnection if a service restarts
                self.connect()
                try:
                    return f(self, *args, **kwargs)
                except (CannotSendRequest, BadStatusLine):
                    log.error("Error sending request for {}, {}".format(args, kwargs))
        except InWarmupError:
            while True:
                log.info("Bitcoin still warming up, retrying...")
                sleep(5)
                try:
                    return f(self, *args, **kwargs)
                except InWarmupError:
                    continue

    return attempt


class BitcoindRPC(object):
    p = None

    def __init__(self, conf):
        self.conf = conf
        self.connect()

    def connect(self):
        self.p = Proxy(service_url=('{}://{}:{}@{}:{}'.format(
            'http',
            self.conf.conf['rpcuser'],
            self.conf.conf['rpcpassword'],
            self.conf.conf['rpcbind'],
            self.conf.conf['rpcport'])))

    @try_robustly
    def get_info(self):
        return self.p.getinfo()

    @try_robustly
    def create_address(self):
        return str(self.p.getnewaddress())

    @try_robustly
    def get_address_balance(self, addr, minconf=0):
        return int2bit(self.p.getreceivedbyaddress(addr, minconf=minconf))

    @try_robustly
    def list_address_amounts(self, minconf=0, include_empty=True):
        # TODO: PR
        addresses = self.p._call('listreceivedbyaddress', minconf, include_empty)
        return dict((a['address'], a['amount']) for a in addresses if a['confirmations'] >= minconf)

    @try_robustly
    def send(self, addr, amount):
        return b2lx(self.p.sendtoaddress(addr, amount))

    @try_robustly
    def get_transaction(self, txid):
        return self.p.gettransaction(lx(txid))

    @try_robustly
    def get_block(self, blockid):
        return self.p.getblock(lx(blockid))

    @try_robustly
    def get_blockchain_info(self):
        return self.p._call('getblockchaininfo')

    @try_robustly
    def generate(self, numblocks):
        return self.p.generate(numblocks)

    @try_robustly
    def list_transactions(self, count=10, skip=0):
        return self.p._call('listtransactions', '*', count, skip)
