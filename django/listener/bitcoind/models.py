from django.db import models

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

    @classmethod
    def generate_mismatched(cls):
        rpc = connect_rpc()

        for a in cls.objects.all():
            amount_bal = -Transaction.balance(a, amount__lt=0)
            amount_btc = rpc.get_address_balance(a.address)

            if amount_bal != amount_btc:
                yield {
                    'btc': amount_btc,
                    'bal': amount_bal,
                    'address': a.serialize_private()
                }

    def deactivate(self):
        self.active = False
        self.save()
        clear_object(self, 'address.serialize')

    def receive(self, amount):
        self.deactivate()
        # TODO: Move this into BTCTransaction
        ok = Transaction.create(source=self,
                                destination=self.user,
                                amount=amount,
                                allow_neg=True)  # BTCTransactions pull addresses negative when they apply
        if not ok:
            log.error("address:{} failed to deposit into user".format(self.uuid))
        clear_object(self, 'address.serialize')

    def serialize_private(self):
        d = self.serialize()
        d['address'] = self.address
        d['active'] = self.active
        # d['transactions'] = list(t.serialize() for t in BTCTransaction.for_address(self))
        return d

    @memoize_key('address.serialize')
    def serialize(self):
        return {
            'id': self.uuid,
            'received': -Transaction.balance(self, amount__lt=0),
            'created': self.created
        }


class Withdrawal(models.Model):
    created = models.DateTimeField(default=now)
    address = BCAddressField()
    amount = models.DecimalField(decimal_places=8, max_digits=12)
    user = models.ForeignKey('user.User')
    txid = models.CharField(max_length=64, null=True)
    token = models.CharField(default=generate_token, max_length=TOKEN_LENGTH, null=True)
    confirmed = models.BooleanField(default=False)
    uuid = models.UUIDField(default=uuid4)

    @classmethod
    def create(cls, user, address, amount):
        for w in cls.outstanding():
            w.deny()

        withdrawal = cls(
            address=address,
            amount=amount,
            user=user)

        withdrawal.save()
        return withdrawal

    @classmethod
    def lookup_uuid(cls, uuid):
        try:
            return cls.objects.get(uuid=uuid)
        except cls.DoesNotExist:
            return None

    @classmethod
    def lookup_token(cls, token):
        try:
            return cls.objects.get(token=token)
        except cls.DoesNotExist:
            return None

    @classmethod
    def outstanding(cls):
        return cls.objects.filter(token__isnull=False, confirmed=False)

    def validate(self):
        if Transaction.balance(self.user) < self.amount:
            self.deny()
            log.info("Withdrawal:{} not confirmed due to insufficient funds".format(self.uuid))
            return False

        if self.confirmed:
            log.info("Withdrawal:{} not confirmed due to already confirmed".format(self.uuid))
            return False

        if self.token is None:
            log.info("Withdrawal:{} not confirmed due to no token".format(self.uuid))
            return False

        return True

    def confirm(self):
        if not self.validate():
            return

        self.confirmed = True
        self.token = None

        try:
            amount = self.amount
            address = self.address
            ok = Transaction.create(source=self.user, destination=self, amount=amount)
            if not ok:
                log.error("withdrawal:{} failed to create transaction".format(self.uuid))
                return

            rpc = connect_rpc()

            try:
                self.txid = rpc.send(address, bit2int(amount))
                record_event('send_btc')
                record_metric('send_btc', amount)
                log.info("Withdrawal {} sent {} to {}, txid {}".format(self.uuid, amount, address, self.txid))
            except Exception as e:
                log.exception("withdrawal:{}, error sending {} to {}".format(self.uuid, amount, address), exc_info=e)

            clear_object(self, 'withdrawal.serialize')
        finally:
            self.save()

    def deny(self):
        self.token = None
        record_event('withdrawal_deny')
        clear_object(self, 'withdrawal.serialize')
        self.save()

    def serialize_private(self):
        d = self.serialize()
        d['address'] = self.address
        d['txid'] = self.txid
        return d

    @memoize_key('withdrawal.serialize')
    def serialize(self):
        return {
            'id': self.uuid,
            'created': self.created,
            'amount': Transaction.balance(self),
            'pending_amount': self.amount
        }


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
        record_event('receive')
        record_metric('receive', self.amount)
        self.applied = True
        self.save()

    def serialize(self):
        return {
            'id': self.uuid,
            'txid': self.txid,
            'address': self.address.address,
            'applied': self.applied,
            'created': self.date,
            'amount': self.amount
        }
