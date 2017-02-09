from decimal import Decimal


def bit2int(b):
    return int(100000000 * b)


def int2bit(i):
    return Decimal(i) / 100000000
