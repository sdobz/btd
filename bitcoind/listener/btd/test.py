import unittest

from .bitcoind import load_confs, start_bitcoind


class TestApplication:
    def __init__(self, rpc):
        self.addresses = {}
        self.rpc = rpc

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


class TestBTD(unittest.TestCase):
    def setUp(self):
        # Fire up server listeners
        confs = load_confs()
        assert 'miner.conf' in confs and 'regtest.conf' in confs
        # Make client
        self.app = TestApplication()
        # Start miner, get rpc connection

        self.miner_rpc
        # Get miner height, premine if <100
        # TODO: consider blockchain state
        pass

    def test_mining_block_triggers_msg(self):
        pass

if __name__ == '__main__':
    unittest.main()
