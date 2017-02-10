from gevent import spawn, sleep
from logging import getLogger
import os
log = getLogger(__name__)
import subprocess

from .conf import BitcoindConf
from .rpc import connect_rpc
from .listener import listen_forever


def fire_and_forget(conf: BitcoindConf):
    subprocess.Popen(['bitcoind', '-conf={}'.format(conf.path()), "-datadir={}".format(conf.datadir())], preexec_fn=os.setsid)


def start_one(conf: BitcoindConf):
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
        fire_and_forget(conf)
        while True:
            try:
                rpc.get_info()
                break
            except ConnectionRefusedError:
                log.info("Retrying...")
                sleep(1)

    log.info("Connection successful, bitcoind:{} is running".format(conf.filename))


def start_all():
    log.info("Starting everything!")
    return [spawn(start_one, conf) for conf in BitcoindConf.enumerate_confs()]
