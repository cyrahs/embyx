import archive
import mapping
import rss
import translate


def main() -> None:
    rss.main()
    archive.main()
    mapping.main()
    translate.main()

if __name__ == '__main__':
    main()
