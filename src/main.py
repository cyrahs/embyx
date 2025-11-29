import time

import archive
import mapping
import rss
from src.core import logger

log = logger.get('main')


def main() -> None:
    rss.main()
    log.info('Wait 10 seconds for magnets ')
    time.sleep(10)
    archive.main()
    mapping.main()

if __name__ == '__main__':
    main()
