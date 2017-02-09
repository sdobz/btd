from django.core.management.base import BaseCommand

from ...listener import start_transaction_listener

from gevent import joinall

import logging
log = logging.getLogger(__name__)


class Command(BaseCommand):
    args = ''
    help = 'A loop that runs all updates'

    def handle(self, *args, **options):
        joinall([
            start_transaction_listener()
        ])
