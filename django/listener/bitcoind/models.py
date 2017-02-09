from django.db import models
from django.utils.timezone import now

from .fields import BCAddressField
from .rpc import connect_rpc
from . import bit2int

from uuid import uuid4
from logging import getLogger
log = getLogger(__name__)


class Address(models.Model):
    address = BCAddressField(db_index=True)
    user = models.ForeignKey('user.User')
    active = models.BooleanField(default=True)
    created = models.DateTimeField(default=now)
    uuid = models.UUIDField(default=uuid4, db_index=True)

    @classmethod
    def create(cls, user):
        rpc = connect_rpc()
        a = cls(address=rpc.create_address(),
                user=user)
        a.save()
        return a

    @classmethod
    def rebuild_addresses(cls):
        log.info("Checking all address balances")
        count = 0
        for a in cls.objects.filter():
            a.check_received()
            count += 1
        log.info("Finished checking {} addresses".format(count))

    @classmethod
    def lookup(cls, addr):
        try:
            return cls.objects.get(address=str(addr))
        except cls.DoesNotExist:
            return None

    @classmethod
    def lookup_uuid(cls, uuid):
        try:
            return cls.objects.get(uuid=uuid)
        except cls.DoesNotExist:
            return None

    @classmethod
    def get_for_user(cls, user):
        user_addresses = cls.objects.filter(user=user, active=True).order_by('-created')[:1]
        for a in user_addresses:
            return a
        return cls.create(user)

    def deactivate(self):
        self.active = False
        self.save()


class BTCTransaction(models.Model):
    txid = models.CharField(max_length=64, db_index=True)
    address = models.ForeignKey(Address, db_index=True)
    date = models.DateTimeField(default=now)
    amount = models.DecimalField(decimal_places=8, max_digits=12)
    applied = models.BooleanField(default=False)
    uuid = models.UUIDField(default=uuid4)

    @classmethod
    def create(cls, txid, address, amount):
        return cls.objects.create(txid=txid, address=address, amount=amount)

    @classmethod
    def lookup(cls, txid, address):
        try:
            return cls.objects.get(txid=txid, address=address)
        except cls.DoesNotExist:
            return None

    @classmethod
    def unapplied(cls):
        return cls.objects.filter(applied=False)

    @classmethod
    def for_address(cls, addr):
        return cls.objects.filter(address=addr)

    def apply(self):
        if self.applied:
            return

        self.address.receive(self.amount)
        self.applied = True
        self.save()
