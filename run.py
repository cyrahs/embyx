import os
import subprocess

from tap import Tap


class Args(Tap):
    script: str | None = None
    """The script to run."""
    script_args: list[str]
    """Arguments for the script."""

    def configure(self) -> None:
        self.add_argument('script', nargs='?')
        self.add_argument('script_args', nargs='...')


def main() -> None:
    parser = Args()
    args = parser.parse_args()
    env = os.environ.copy()
    env['PYTHONPATH'] = '.'
    cmd = ['.venv/bin/python', f'src/{args.script}.py', *args.script_args] if args.script else ['.venv/bin/python', 'src/main.py']
    subprocess.run(cmd, env=env, check=True)  # noqa: S603


if __name__ == '__main__':
    main()
