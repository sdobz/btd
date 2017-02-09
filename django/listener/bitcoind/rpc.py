from django.conf import settings

from gevent import sleep

from . import int2bit
from bitcoin.rpc import Proxy, InWarmupError
from bitcoin.core import b2lx, lx
from bitcoin.wallet import CBitcoinAddress, CBitcoinAddressError
from bitcoin.base58 import Base58ChecksumError, InvalidBase58Error
from httplib import CannotSendRequest, BadStatusLine
from logging import getLogger
log = getLogger(__name__)


conn = None


def address_valid(address):
    try:
        CBitcoinAddress(address)
        return True
    except (CBitcoinAddressError, Base58ChecksumError, InvalidBase58Error):
        return False


def connect_rpc():
    global conn
    if conn is None:
        conn = Bitcoin()
    return conn


def retry_once(f):
    def attempt(self, *args, **kwargs):
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

    def __init__(self):
        self.connect()

    def connect(self):
        self.p = Proxy(service_url=('%s://%s:%s@%s:%d' %
                    ('http', settings.BITCOIN_RPC_USER, settings.BITCOIN_RPC_PASSWORD, 'bitcoin', 18332)))

    @retry_once
    @profile_function
    def create_address(self):
        return str(self.p.getnewaddress())

    @retry_once
    @profile_function
    def get_address_balance(self, addr, minconf=0):
        return int2bit(self.p.getreceivedbyaddress(addr, minconf=minconf))

    @retry_once
    @profile_function
    def list_address_amounts(self, minconf=0, include_empty=True):
        # TODO: PR
        addresses = self.p._call('listreceivedbyaddress', minconf, include_empty)
        return dict((a['address'], a['amount']) for a in addresses if a['confirmations'] >= minconf)

    @retry_once
    @profile_function
    def send(self, addr, amount):
        return b2lx(self.p.sendtoaddress(addr, amount))

    @retry_once
    @profile_function
    def get_transaction(self, txid):
        return self.p.gettransaction(lx(txid))

    @retry_once
    @profile_function
    def get_block(self, blockid):
        return self.p.getblock(lx(blockid))

    @retry_once
    @profile_function
    def get_blockchain_info(self):
        return self.p._call('getblockchaininfo')
