import zmq.green as zmq

from gevent import Greenlet

from ..bitcoind.rpc import connect_rpc

import struct

from .models import Address, BTCTransaction

from decimal import Decimal
from logging import getLogger
log = getLogger(__name__)

import binascii

# TODO: move to settings
port = 8330

seq = {}


def sequence_increments(new_seq, topic):
    global seq
    old = seq[topic] if topic in seq else 0
    increments = new_seq - old == 1
    seq[topic] = new_seq
    return increments


def listen(zmqSubSocket):
    while True:
        try:
            msg = zmqSubSocket.recv_multipart()
            topic = str(msg[0])
            if topic != "hashtx" and topic != "hashblock":
                continue

            # Sequence checking
            if len(msg[-1]) == 4:
                new_seq = struct.unpack('<I', msg[-1])[-1]

            if not sequence_increments(new_seq, topic):
                log.warning("bitcoin:sequence".format(
                    topic, new_seq))

            body = msg[1]
            hash = binascii.b2a_hex(body)

            if topic == "hashtx":
                # TODO: Detect message type here?
                handle_txid(hash)
            if topic == "hashblock":
                handle_blockid(hash)

        except Exception as e:
            log.exception("Uncaught exception during bitcoin ZMQ listen", exc_info=e)


def handle_txid(txid):
    rpc = connect_rpc()
    try:
        tx_dat = rpc.get_transaction(txid)
    except IndexError:
        # Not our problem (non wallet)
        return

    if 'txid' not in tx_dat or 'details' not in tx_dat or 'confirmations' not in tx_dat:
        log.error("tx:{} malformed".format(txid))
        return

    for det in tx_dat['details']:
        if 'category' not in det or 'address' not in det or 'amount' not in det:
            log.error("tx:{} malformed detail".format(txid))
            continue

        if det['category'] != 'receive':
            continue

        addr = det['address']

        a = Address.lookup(addr)
        if a is None:
            log.error("tx:{} included address:{} not in db".format(txid, det['address']))
            continue

        value = Decimal(det['amount'])

        try:
            btct = BTCTransaction.lookup(txid, a)
        except BTCTransaction.MultipleObjectsReturned:
            log.error("Multiple transaction records found for tx:{} address:{}".format(txid, addr))
            continue

        a.deactivate()
        log.info("address:{} saw {} BTC, tx:{}".format(addr, value, txid))


def handle_blockid(blockid):
    log.info("Got new block:{}".format(blockid))

    # Luckily this does!
    for btct in BTCTransaction.unapplied():
        handle_txid(btct.txid)


def start_transaction_listener():
    log.info("Starting transaction listener")
    zmqContext = zmq.Context()
    zmqSubSocket = zmqContext.socket(zmq.SUB)
    zmqSubSocket.setsockopt(zmq.SUBSCRIBE, "hashblock")
    zmqSubSocket.setsockopt(zmq.SUBSCRIBE, "hashtx")
    # zmqSubSocket.setsockopt(zmq.SUBSCRIBE, "rawblock")
    # zmqSubSocket.setsockopt(zmq.SUBSCRIBE, "rawtx")
    zmqSubSocket.connect("tcp://bitcoin:%i" % port)

    g = Greenlet(listen, zmqSubSocket)
    g.start()
    return g
