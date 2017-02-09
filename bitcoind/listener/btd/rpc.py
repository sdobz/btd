from gevent import sleep

from . import int2bit
from .conf import BitcoindConf

from bitcoin.rpc import Proxy, InWarmupError
from bitcoin.core import b2lx, lx
from bitcoin.wallet import CBitcoinAddress, CBitcoinAddressError
from bitcoin.base58 import Base58ChecksumError, InvalidBase58Error
from http.client import CannotSendRequest, BadStatusLine
from logging import getLogger

log = getLogger(__name__)


def address_valid(address):
    try:
        CBitcoinAddress(address)
        return True
    except (CBitcoinAddressError, Base58ChecksumError, InvalidBase58Error):
        return False


conn = {}


def connect_rpc(conf: BitcoindConf):
    global conn
    if conf.filename not in conn:
        conn[conf.filename] = Bitcoin(conf)
    return conn[conf.filename]


def retry_once(f):
    def attempt(self, *args, **kwargs):
        try:
            try:
                return f(self, *args, **kwargs)
            except (CannotSendRequest, BadStatusLine):
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


class Bitcoin(object):
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

    @retry_once
    def get_info(self):
        return self.p.getinfo()

    @retry_once
    def create_address(self):
        return str(self.p.getnewaddress())

    @retry_once
    def get_address_balance(self, addr, minconf=0):
        return int2bit(self.p.getreceivedbyaddress(addr, minconf=minconf))

    @retry_once
    def list_address_amounts(self, minconf=0, include_empty=True):
        # TODO: PR
        addresses = self.p._call('listreceivedbyaddress', minconf, include_empty)
        return dict((a['address'], a['amount']) for a in addresses if a['confirmations'] >= minconf)

    @retry_once
    def send(self, addr, amount):
        return b2lx(self.p.sendtoaddress(addr, amount))

    @retry_once
    def get_transaction(self, txid):
        return self.p.gettransaction(lx(txid))

    @retry_once
    def get_block(self, blockid):
        return self.p.getblock(lx(blockid))

    @retry_once
    def get_blockchain_info(self):
        return self.p._call('getblockchaininfo')
