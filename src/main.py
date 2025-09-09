import archive
import mapping
import rss


def main() -> None:
    rss.main()
    archive.main()
    mapping.main()

if __name__ == '__main__':
    main()
