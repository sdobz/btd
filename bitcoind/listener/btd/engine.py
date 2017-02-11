import zmq.green as zmq

from .bitcoind import BitcoindRPC, BitcoindConf
from . import settings

import struct
from hashlib import md5

from decimal import Decimal
from logging import getLogger
log = getLogger(__name__)

import binascii
import sqlite3
from datetime import datetime
from dateutil.parser import parse as dateutil_parse
from collections import namedtuple
from os import path
import json

from uuid import uuid4


class BtdListener:
    TxInfo = namedtuple('TxInfo', 'uuid change category txid addr context amount confirmations orig')

    def __init__(self, conf: BitcoindConf, rpc: BitcoindRPC=None, storage: BtdStorage=None):
        self.conf = conf
        self.rpc = rpc or BitcoindRPC(conf)
        self.storage = storage or BtdStorage(conf)
        self.seq = {}

    def sequence_increments(self, new_seq, topic):
        old = self.seq[topic] if topic in self.seq else 0
        increments = new_seq - old == 1
        self.seq[topic] = new_seq
        return increments

    def listen_forever(self):
        confd = self.conf.conf
        if 'zmqpubhashtx' not in confd or 'zmqpubhashblock' not in confd:
            log.info("Did not detect zmqpubhashtx and zmqpubhashblock in conf:{}, not listening".format(self.conf.filename))
            return

        zmqContext = zmq.Context()
        zmqSubSocket = zmqContext.socket(zmq.SUB)
        zmqSubSocket.setsockopt_string(zmq.SUBSCRIBE, "hashblock")
        zmqSubSocket.setsockopt_string(zmq.SUBSCRIBE, "hashtx")
        # zmqSubSocket.setsockopt(zmq.SUBSCRIBE, "rawblock")
        # zmqSubSocket.setsockopt(zmq.SUBSCRIBE, "rawtx")
        zmqSubSocket.connect(confd['zmqpubhashtx'])

        while True:
            try:
                msg = zmqSubSocket.recv_multipart()
                topic = str(msg[0])
                if topic != "hashtx" and topic != "hashblock":
                    continue

                log.info("GOT MSG: {}".format(topic))

                # Sequence checking
                if len(msg[-1]) == 4:
                    new_seq = struct.unpack('<I', msg[-1])[-1]

                    if not self.sequence_increments(new_seq, topic):
                        # Missed something
                        self.rebuild_tx()

                if topic == "hashtx":
                    txid = binascii.b2a_hex(msg[1])
                    self.handle_txid(txid)
                if topic == "hashblock":
                    self.rebuild_tx()

            except Exception as e:
                log.exception("Uncaught exception during bitcoin ZMQ listen", exc_info=e)

    def handle_txid(self, txid):
        try:
            tx_dat = self.rpc.get_transaction(txid)
        except IndexError:
            # Not our problem (non wallet)
            return

        self.rebuild_tx()

    def handle_blockid(self, blockid):
        log.info("Got new block:{}".format(blockid))
        self.rebuild_tx()

    def rebuild_tx(self):
        # TODO: count?
        txs = set(self.rpc.list_transactions(count=100))
        low_conf_txs = set(filter(txs, lambda tx_dat: 'confirmations' in tx_dat and tx_dat['confirmations'] < 10))

        db_txaddr = self.storage.load_txs(tx_dat['txid'] for tx_dat in low_conf_txs)

        log.info("Using {}% of rpc'd transactions".format((len(low_conf_txs)/len(txs))*100))

        for tx_dat in low_conf_txs:
            diff = self.diff_tx(tx_dat, db_txaddr)
            if diff:
                self.broadcast_diff(diff)

        # TODO: mark disappeared transactions

    def diff_tx(self, tx_dat, db_txaddr):
        # Modifies db_txaddr

        if 'txid' not in tx_dat or \
                'category' not in tx_dat or \
                'address' not in tx_dat or \
                'confirmations' not in tx_dat or \
                'amount' not in tx_dat:
            log.error("tx:{} malformed".format(tx_dat['txid']))
            return

        txid = tx_dat['txid']

        if txid not in db_txaddr:
            change = 'new'
            self.storage.store_tx_dat(tx_dat)
            context = self.storage.lookup_context(tx_dat['address'])
        else:
            tx, addr = db_txaddr[txid]
            del db_txaddr[txid]
            context = addr.context

            amount = Decimal(tx_dat['amount'])
            confirmations = tx_dat['confirmations']

            if amount == tx.amount and confirmations == tx.confirmations:
                return None

            change = 'modified'
            self.storage.store_tx_dat(tx_dat)

        return self.TxInfo(
            uuid=uuid4(),
            change=change,
            category=tx_dat['category'],
            txid=tx_dat['txid'],
            addr=tx_dat['address'],
            context=context,
            amount=Decimal(tx_dat['amount']),
            confirmations=tx_dat['confirmations'],
            orig=tx_dat)

    def broadcast_diff(self, txinfo: TxInfo):
        log.info(txinfo)


class BtdRPC:
    def __init__(self, conf: BitcoindConf, rpc: BitcoindRPC=None, storage: BtdStorage=None):
        self.conf = conf
        self.rpc = rpc or BitcoindRPC(conf)
        self.storage = storage or BtdStorage(conf)

    def get_address(self, context):
        return self.storage.lookup_unused_address(context) or self.storage.store_address(self.rpc.create_address(), context)

    def send(self, address, amount, context):
        self.storage.store_address(address, context)
        self.rpc.send(address, amount)


class BtdStorage:
    AddrRow = namedtuple('addr', 'rowid address context contexthash created modified')
    TxRow = namedtuple('tx', 'rowid uuid txid addrid amount confirmations orig silenced created modified')

    def __init__(self, conf: BitcoindConf):
        self.conf = conf
        self.db = sqlite3.connect(path.join(settings.BTD_SQLITE_DIR, conf.filename + '.sqlite'), detect_types=sqlite3.PARSE_DECLTYPES)
        self.db.execute('CREATE TABLE IF NOT EXISTS addr ('
                        'address VARCHAR(34) UNIQUE,'
                        'context BLOB NULL,'
                        'contexthash VARCHAR(32) NULL,'
                        'created DATETIME,'
                        'modified DATETIME)')
        self.db.execute('CREATE TABLE IF NOT EXISTS tx ('
                        'uuid VARCHAR(36),'
                        'txid VARCHAR(64),'
                        'FOREIGN KEY (addrid) REFERENCES addr(rowid),'
                        'amount DECIMAL,'
                        'confirmations INTEGER,'
                        'orig BLOB,'
                        'silenced BOOL,'
                        'created DATETIME,'
                        'modified DATETIME)')

    def lookup_unused_address(self, context):
        contexthash = self.hash_context(context)

        return self.db.execute(
            'SELECT address FROM addr'
            ' LEFT JOIN tx ON tx.addrid = addr.rowid'
            ' WHERE addr.contexthash=? AND tx.addrid IS NULL'
            ' LIMIT 1', contexthash).fetchone()

    def lookup_context(self, address):
        return self.db.execute(
            'SELECT context FROM addr WHERE address=?', address).fetchone()

    def get_address_rowid(self, address):
        rowid = self.db.execute('SELECT rowid FROM addr WHERE address=?', address).fetchone()
        if rowid is None:
            rowid =

    def store_address(self, addr, context=None):
        c = self.db.cursor()
        contexthash = self.hash_context(context) if context is not None else None
        now = datetime.now()
        c.execute('UPDATE addr SET'
                  ' context=?, contexthash=?, modified=? WHERE addr=?',
                  (context, contexthash, now, addr))
        c.execute('INSERT INTO addr (addr, context, contexthash, created, modified)'
                  ' SELECT ?, ?, ?, ?, ? WHERE (SELECT Changes() = 0)',
                  (addr, context, contexthash, now, now))
        self.db.commit()
        c.close()
        return addr

    def load_txs(self, txids):
        tx_rows = {}
        c = self.db.cursor()
        c.execute('SELECT ? FROM tx WHERE txid IN ?',
                  (','.join(self.TxRow._fields), txids))
        for row in c:
            tx = self.TxRow._make(row)
            tx_rows[tx.txid] = tx

        return tx_rows

    def store_tx_dat(self, tx_dat):
        addrid = self.get_address_rowid(tx_dat['address'])
        amount = Decimal(tx_dat['amount'])

        c = self.db.cursor()
        now = datetime.now()
        c.execute('UPDATE tx SET'
                  ' addrid=?, amount=?, confirmations=?, orig=?, silenced=?, modified=? WHERE txid=?',
                  (addrid, amount, tx_dat['confirmations'], json.dumps(tx_dat), False, now, tx_dat['txid']))
        c.execute('INSERT INTO tx (uuid, txid, addrid,  amount, confirmations, orig, silenced, created, modified)'
                  ' SELECT ?, ?, ?, ?, ?, ?, ?, ?, ? WHERE (SELECT Changes() = 0)',
                  (uuid4(), tx_dat['txid'], addrid, amount, tx_dat['confirmations'], json.dumps(tx_dat), False, now, now))
        self.db.commit()
        c.close()

    @staticmethod
    def hash_context(context):
        return md5(context).hexdigest()

sqlite3.register_adapter(Decimal, lambda d: str(d))
sqlite3.register_converter("DECIMAL", lambda s: Decimal(s))
sqlite3.register_adapter(datetime, lambda dt: dt.isoformat(dt))
sqlite3.register_converter("DATETIME", lambda s: dateutil_parse(s))


"""
listtransactions ( "account" count from includeWatchonly)

Returns up to 'count' most recent transactions skipping the first 'from' transactions for account 'account'.

Arguments:
1. "account"    (string, optional) DEPRECATED. The account name. Should be "*".
2. count          (numeric, optional, default=10) The number of transactions to return
3. from           (numeric, optional, default=0) The number of transactions to skip
4. includeWatchonly (bool, optional, default=false) Include transactions to watchonly addresses (see 'importaddress')

Result:
[
  {
    "account":"accountname",       (string) DEPRECATED. The account name associated with the transaction.
                                                It will be "" for the default account.
    "address":"bitcoinaddress",    (string) The bitcoin address of the transaction. Not present for
                                                move transactions (category = move).
    "category":"send|receive|move", (string) The transaction category. 'move' is a local (off blockchain)
                                                transaction between accounts, and not associated with an address,
                                                transaction id or block. 'send' and 'receive' transactions are
                                                associated with an address, transaction id and block details
    "amount": x.xxx,          (numeric) The amount in BTC. This is negative for the 'send' category, and for the
                                         'move' category for moves outbound. It is positive for the 'receive' category,
                                         and for the 'move' category for inbound funds.
    "vout": n,                (numeric) the vout value
    "fee": x.xxx,             (numeric) The amount of the fee in BTC. This is negative and only available for the
                                         'send' category of transactions.
    "abandoned": xxx          (bool) 'true' if the transaction has been abandoned (inputs are respendable).
    "confirmations": n,       (numeric) The number of confirmations for the transaction. Available for 'send' and
                                         'receive' category of transactions. Negative confirmations indicate the
                                         transaction conflicts with the block chain
    "trusted": xxx            (bool) Whether we consider the outputs of this unconfirmed transaction safe to spend.
    "blockhash": "hashvalue", (string) The block hash containing the transaction. Available for 'send' and 'receive'
                                          category of transactions.
    "blockindex": n,          (numeric) The index of the transaction in the block that includes it. Available for 'send' and 'receive'
                                          category of transactions.
    "blocktime": xxx,         (numeric) The block time in seconds since epoch (1 Jan 1970 GMT).
    "txid": "transactionid", (string) The transaction id. Available for 'send' and 'receive' category of transactions.
    "time": xxx,              (numeric) The transaction time in seconds since epoch (midnight Jan 1 1970 GMT).
    "timereceived": xxx,      (numeric) The time received in seconds since epoch (midnight Jan 1 1970 GMT). Available
                                          for 'send' and 'receive' category of transactions.
    "comment": "...",       (string) If a comment is associated with the transaction.
    "label": "label"        (string) A comment for the address/transaction, if any
    "otheraccount": "accountname",  (string) For the 'move' category of transactions, the account the funds came
                                          from (for receiving funds, positive amounts), or went to (for sending funds,
                                          negative amounts).
    "bip125-replaceable": "yes|no|unknown"  (string) Whether this transaction could be replaced due to BIP125 (replace-by-fee);
                                                     may be unknown for unconfirmed transactions not in the mempool
  }
]

Examples:

List the most recent 10 transactions in the systems
> bitcoin-cli listtransactions

List transactions 100 to 120
> bitcoin-cli listtransactions "*" 20 100

As a json rpc call
> curl --user myusername --data-binary '{"jsonrpc": "1.0", "id":"curltest", "method": "listtransactions", "params": ["*", 20, 100] }' -H 'content-type: text/plain;' http://127.0.0.1:8332/
"""