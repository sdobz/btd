import unittest
from logging.config import dictConfig
import logging
logging_config = dict(
    version=1,
    formatters={
        'f': {
            'format':
                '%(asctime)s %(name)-12s %(levelname)-8s %(message)s'}
    },
    handlers={
        'h': {
            'class': 'logging.StreamHandler',
            'formatter': 'f',
            'level': logging.DEBUG,
            'stream': 'ext://sys.stderr'
        }
    },
    root={
        'handlers': ['h'],
        'level': logging.DEBUG,
    },
)
dictConfig(logging_config)
log = logging.getLogger(__name__)

from btd.bitcoind import load_confs, start_bitcoind, BitcoindRPC
from btd.engine import BtdListener

from gevent import spawn, sleep, joinall
from decimal import Decimal

class TestApplication:
    def __init__(self, conf):
        self.addresses = {}
        self.conf = conf

    def reset(self):
        pass

    def messages(self, address):
        return 0

    def balance(self, address):
        return 0

    def create_address(self):
        self.addresses = {}

    def handle_message(self):
        # self.addresses[address][uuid] = <json structure>
        pass

    def listen(self):
        # spawn callback listener
        pass


class TestIntegration(unittest.TestCase):
    def setUp(self):
        # Fire up server listeners
        confs = load_confs()
        assert 'miner.conf' in confs and 'regtest.conf' in confs

        confs['miner.conf'].clean_regtest()
        confs['regtest.conf'].clean_regtest()

        joinall((
            spawn(start_bitcoind, confs['miner.conf']),
            spawn(start_bitcoind, confs['regtest.conf'])))

        # Make client
        self.app = TestApplication(confs['regtest.conf'])

        # Listen for events from regtest.conf
        listener = BtdListener(confs['regtest.conf'])
        self.listenlet = spawn(listener.listen_forever)
        self.minerRPC = BitcoindRPC(confs['miner.conf'])
        self.testRPC = BitcoindRPC(confs['regtest.conf'])

    def test_mining_block_triggers_msg(self):
        log.info("Generating block...")
        self.minerRPC.generate(101)
        addr = self.testRPC.create_address()
        log.info("Test generated address:{}".format(addr))
        log.info("Miner wallet info:")
        log.info(self.minerRPC.get_wallet_info())
        log.info("Miner sending .1x20 to addr")
        for i in range(20):
            self.minerRPC.send(addr, Decimal(.1))
        log.info("Generating block to confirm tx")
        self.minerRPC.generate(1)
        log.info("Test wallet info:")
        log.info(self.testRPC.get_wallet_info())


if __name__ == '__main__':
    unittest.main()
