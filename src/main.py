import time

import archive
import mapping
import rss
from src.core import logger

log = logger.get('main')


def main() -> None:
    rss.main()
    archive.main()
    mapping.main()

if __name__ == '__main__':
    main()
