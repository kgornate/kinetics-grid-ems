#!/usr/bin/env python3
from __future__ import annotations

import getpass
import sys

from nb_ems_gateway.auth.security import make_password_hash


def main() -> None:
    password = sys.argv[1] if len(sys.argv) > 1 else getpass.getpass('Password: ')
    print(make_password_hash(password))


if __name__ == '__main__':
    main()
