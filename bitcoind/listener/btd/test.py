import unittest


class TestApplication:
    def __init__(self):
        self.addresses = {}
        self.client = None  # Make client and connect

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
        # Make client
        # Start miner, get rpc connection
        # Get miner height, premine if <100
        # TODO: consider blockchain state
        pass

    def test_mining_block_triggers_msg(self):
        pass

if __name__ == '__main__':
    unittest.main()
