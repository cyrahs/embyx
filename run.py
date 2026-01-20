import asyncio
from pathlib import Path

from tap import Tap

from src import archive, fill_actor, mapping, merge, monitor, rss

COMMANDS = ('archive', 'fill_actor', 'mapping', 'merge', 'monitor', 'rss')


class Args(Tap):
    command: str
    command_args: list[str]

    def configure(self) -> None:
        self.add_argument('command', choices=COMMANDS)
        self.add_argument('command_args', nargs='...')


class RssArgs(Tap):
    rank: bool = False

    def configure(self) -> None:
        self.add_argument('-r', '--rank', action='store_true', help='get magnets from rank category')


class FillActorArgs(Tap):
    actor_ids: list[str]

    def configure(self) -> None:
        self.add_argument('actor_ids', nargs='+', help='actor_ids in javbus like 11w6')


class MergeArgs(Tap):
    search_dir: Path
    dst_dir: Path
    filter: str

    def configure(self) -> None:
        self.add_argument('search_dir', type=Path, default='type/vr', help='search directory')
        self.add_argument('dst_dir', type=Path, help='destination directory')
        self.add_argument('-f', '--filter', type=str, default='', help='filter to merge')


def main() -> None:
    parser = Args()
    args = parser.parse_args()
    command_args = args.command_args or []
    if args.command == 'archive':
        if command_args:
            parser.error('archive does not accept arguments')
        archive.main()
    elif args.command == 'mapping':
        if command_args:
            parser.error('mapping does not accept arguments')
        mapping.main()
    elif args.command == 'monitor':
        if command_args:
            parser.error('monitor does not accept arguments')
        asyncio.run(monitor.main())
    elif args.command == 'rss':
        rss_args = RssArgs().parse_args(command_args)
        asyncio.run(rss.main(rank=rss_args.rank))
    elif args.command == 'fill_actor':
        fill_args = FillActorArgs().parse_args(command_args)
        asyncio.run(fill_actor.main(fill_args.actor_ids))
    elif args.command == 'merge':
        merge_args = MergeArgs().parse_args(command_args)
        merge.main(merge_args.search_dir, merge_args.dst_dir, merge_args.filter)
    else:
        parser.error(f'Unknown command: {args.command}')


if __name__ == '__main__':
    main()
