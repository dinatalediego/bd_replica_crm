"""Run after installing the publishing extra; never loads .env automatically."""
from replica_cygnus.publishing.cli import main

if __name__ == '__main__':
    raise SystemExit(main())
