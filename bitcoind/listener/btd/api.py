import zmq
from .settings import BTD_RPC_PORT
from logging import getLogger
log = getLogger(__name__)


def listen_rpc():
    context = zmq.Context()
    socket = context.socket(zmq.REP)
    # TODO: mask to docker ips
    socket.bind("tcp://*:{}".format(BTD_RPC_PORT))

    while True:
        msg = socket.recv_multipart()
        rp = str(msg[0])
        log.info("Got req:{}".format(rp))
        socket.send("reply")


def getinfo():
    return

def make_publisher():
    pass
