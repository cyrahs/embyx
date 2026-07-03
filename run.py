import asyncio
from pathlib import Path

from tap import Tap

from src import archive, fill_actor, mapping, merge, monitor, rss
from src.utils.cleanup import aclose_all

COMMANDS = ('archive', 'fill_actor', 'mapping', 'merge', 'monitor', 'rss')
_cleanup_tasks: set[asyncio.Task[None]] = set()


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


async def _run_async_with_cleanup(awaitable) -> None:  # noqa: ANN001
    try:
        await awaitable
    finally:
        await aclose_all()


def _run_sync_with_cleanup(func, *args) -> None:  # noqa: ANN001, ANN002
    try:
        func(*args)
    finally:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(aclose_all())
        else:
            task = loop.create_task(aclose_all())
            _cleanup_tasks.add(task)
            task.add_done_callback(_cleanup_tasks.discard)


def main() -> None:
    parser = Args()
    args = parser.parse_args()
    command_args = args.command_args or []
    if args.command == 'archive':
        if command_args:
            parser.error('archive does not accept arguments')
        _run_sync_with_cleanup(archive.main)
    elif args.command == 'mapping':
        if command_args:
            parser.error('mapping does not accept arguments')
        _run_sync_with_cleanup(mapping.main)
    elif args.command == 'monitor':
        if command_args:
            parser.error('monitor does not accept arguments')
        asyncio.run(_run_async_with_cleanup(monitor.main()))
    elif args.command == 'rss':
        rss_args = RssArgs().parse_args(command_args)
        asyncio.run(_run_async_with_cleanup(rss.main(rank=rss_args.rank)))
    elif args.command == 'fill_actor':
        fill_args = FillActorArgs().parse_args(command_args)
        asyncio.run(_run_async_with_cleanup(fill_actor.main(fill_args.actor_ids)))
    elif args.command == 'merge':
        merge_args = MergeArgs().parse_args(command_args)
        _run_sync_with_cleanup(merge.main, merge_args.search_dir, merge_args.dst_dir, merge_args.filter)
    else:
        parser.error(f'Unknown command: {args.command}')


if __name__ == '__main__':
    main()
