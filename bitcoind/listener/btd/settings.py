import os

BITCOIN_CONF_DIR = '/etc/bitcoin'
BITCOIN_DATA_DIR = '/var/bitcoin'
BTD_PUB_PORT = 10033
BTD_RPC_PORT = 10044
BTD_SQLITE_DIR = '/var/btd/'

from bitcoin import SelectParams
SelectParams('regtest')
