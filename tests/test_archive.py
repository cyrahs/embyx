# tests/test_archive.py
from __future__ import annotations

import importlib
import os
import re
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import Mock, call

import pytest


class ArchiveModuleImportError(ImportError):
    def __init__(self, candidates: list[str]) -> None:
        message = (
            "Unable to import the target archive module. Set ARCHIVE_MODULE to the module path.\n"
            "Example: ARCHIVE_MODULE=src.archive pytest -q\n"
            f"Tried candidates: {candidates}"
        )
        super().__init__(message)


def _import_archive_module() -> ModuleType:
    """Import the archive module via ARCHIVE_MODULE when needed.

    If the real module path is unknown (e.g. src.archive or src.jobs.archive),
    set ARCHIVE_MODULE to point to it.

    Usage:
      ARCHIVE_MODULE=src.archive pytest -q
    """
    env_name = os.environ.get("ARCHIVE_MODULE")
    candidates = []
    if env_name:
        candidates.append(env_name)

    # Common candidates (add or remove as needed).
    candidates += [
        "src.archive",
        "archive",
        "src.scripts.archive",
        "src.jobs.archive",
        "src.tasks.archive",
    ]

    last_exc = None
    required_symbols = {
        "remove_00",
        "check_exists",
        "multi_part_video_check",
        "is_4k_video",
        "normalize_copy_suffix",
        "drop_duplicate_copies",
        "rename",
        "flatten",
        "clear_dirname",
        "find_dst_dir",
        "find_video_dst",
        "archive",
        "main",
    }

    for name in candidates:
        try:
            mod = importlib.import_module(name)
            if all(hasattr(mod, s) for s in required_symbols):
                return mod
        except Exception as exc:  # noqa: BLE001
            last_exc = exc

    raise ArchiveModuleImportError(candidates) from last_exc


def _write_bytes(p: Path, size: int = 1) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"0" * size)
    return p


@pytest.fixture
def mod(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> ModuleType:
    """Monkeypatch external dependencies to isolate script logic from the real environment."""
    m = _import_archive_module()

    # 1) Logging: the script uses notice/info/warning/exception.
    monkeypatch.setattr(m, "log", Mock())

    # 2) Config: the script relies on cfg.min_size / cfg.brand_mapping / cfg.src_dir / cfg.dst_dir / cfg.mapping.
    cfg = SimpleNamespace(
        min_size=0,  # MB, default 0: any file with size > 0 counts.
        brand_mapping={},  # Default: no mapping.
        src_dir=tmp_path / "cfg_src",
        dst_dir=tmp_path / "cfg_dst",
        mapping={},
    )
    cfg.src_dir.mkdir(parents=True, exist_ok=True)
    cfg.dst_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(m, "cfg", cfg, raising=False)

    # 3) time.sleep: avoid a real 5-second sleep.
    monkeypatch.setattr(m.time, "sleep", Mock(), raising=True)

    # 4) Utils stubs aligned to the script behavior.
    video_suffixes = {".mp4", ".mkv", ".avi"}

    def is_video(p: Path) -> bool:
        return p.is_file() and p.suffix.lower() in video_suffixes

    def has_video_suffix(p: Path) -> bool:
        # In clear_dirname, folder is a directory, but suffix still returns ".mp4".
        return p.suffix.lower() in video_suffixes

    def get_avid(name: str) -> str:
        # Match IDs like ABP-00123 / ABP-123 to approximate business logic.
        mm = re.search(r"([A-Z0-9]+-\d+)", name)
        return mm.group(1) if mm else ""

    def get_brand(avid: str) -> str:
        # Default brand is the avid prefix.
        if avid and "-" in avid:
            return avid.split("-", 1)[0]
        return ""

    monkeypatch.setattr(m, "is_video", is_video, raising=False)
    monkeypatch.setattr(m, "has_video_suffix", has_video_suffix, raising=False)
    monkeypatch.setattr(m, "get_avid", get_avid, raising=False)
    monkeypatch.setattr(m, "get_brand", get_brand, raising=False)

    return m


# ---------------------------
# remove_00
# ---------------------------


def test_remove_00_removes_first_00_when_match(mod: ModuleType) -> None:
    mod.log.reset_mock()
    assert mod.remove_00("ABP-00123") == "ABP-123"
    mod.log.info.assert_called_once()


def test_remove_00_removes_first_00_for_4_digits_tail(mod: ModuleType) -> None:
    # "-000123" matches: 00 + 4 digits (0123) => drop the first 00.
    assert mod.remove_00("ABP-000123") == "ABP-0123"


def test_remove_00_no_change_when_not_match(mod: ModuleType) -> None:
    mod.log.reset_mock()
    assert mod.remove_00("ABP-123") == "ABP-123"
    mod.log.info.assert_not_called()


# ---------------------------
# check_exists
# ---------------------------


def test_check_exists_true_if_video_with_prefix(mod: ModuleType, tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    _write_bytes(root / "ABP-123.mp4", 10)
    (root / "ABP-123.txt").write_text("x", encoding="utf-8")
    assert mod.check_exists("ABP-123", root) is True


def test_check_exists_false_if_only_non_video(mod: ModuleType, tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "ABP-123.txt").write_text("x", encoding="utf-8")
    assert mod.check_exists("ABP-123", root) is False


def test_check_exists_false_if_other_prefix(mod: ModuleType, tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    _write_bytes(root / "XYZ-999.mp4", 10)
    assert mod.check_exists("ABP-123", root) is False


# ---------------------------
# multi_part_video_check
# ---------------------------


def test_multi_part_video_check_raises_for_single(mod: ModuleType, tmp_path: Path) -> None:
    v = tmp_path / "a.mp4"
    with pytest.raises(ValueError, match="only one video file"):
        mod.multi_part_video_check([v])


def test_multi_part_video_check_true_when_only_digits_differ(mod: ModuleType, tmp_path: Path) -> None:
    videos = [tmp_path / "ABP-123-1.mp4", tmp_path / "ABP-123-2.mp4"]
    assert mod.multi_part_video_check(videos) is True


def test_multi_part_video_check_true_for_letter_index(mod: ModuleType, tmp_path: Path) -> None:
    videos = [tmp_path / "movie-A.mp4", tmp_path / "movie-B.mp4"]
    assert mod.multi_part_video_check(videos) is True


def test_multi_part_video_check_false_for_unrelated(mod: ModuleType, tmp_path: Path) -> None:
    videos = [tmp_path / "a1.mp4", tmp_path / "b2.mp4"]
    assert mod.multi_part_video_check(videos) is False


# ---------------------------
# is_4k_video
# ---------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("ABP-123-4k.mp4", True),
        ("ABP-123_4K.mkv", True),
        ("ABP-1234k.mp4", False),   # 4k preceded by a digit
        ("something4k.mp4", False), # 4k preceded by a letter
        ("4k.mp4", False),          # stem == "4k"
        ("video.mp4", False),
    ],
)
def test_is_4k_video(mod: ModuleType, tmp_path: Path, name: str, *, expected: bool) -> None:
    assert mod.is_4k_video(tmp_path / name) is expected


# ---------------------------
# normalize_copy_suffix
# ---------------------------


@pytest.mark.parametrize(
    ("stem", "expected"),
    [
        ("ABP-123 (1)", "ABP-123"),
        ("ABP-123(2)", "ABP-123"),
        ("ABP-123 (abc)", "ABP-123 (abc)"),
        ("ABP-123 (1) extra", "ABP-123 (1) extra"),
    ],
)
def test_normalize_copy_suffix(mod: ModuleType, stem: str, expected: str) -> None:
    assert mod.normalize_copy_suffix(stem) == expected


# ---------------------------
# drop_duplicate_copies
# ---------------------------


def test_drop_duplicate_copies_drops_when_base_exists(mod: ModuleType, tmp_path: Path) -> None:
    folder = tmp_path / "f"
    folder.mkdir()

    base = _write_bytes(folder / "ABP-123.mp4", 10)
    c1 = _write_bytes(folder / "ABP-123 (1).mp4", 10)
    c2 = _write_bytes(folder / "ABP-123(2).mp4", 10)

    res = mod.drop_duplicate_copies(folder, [base, c1, c2])

    assert res == [base]
    assert base.exists()
    assert not c1.exists()
    assert not c2.exists()


def test_drop_duplicate_copies_keeps_when_only_copies(mod: ModuleType, tmp_path: Path) -> None:
    folder = tmp_path / "f"
    folder.mkdir()

    c1 = _write_bytes(folder / "ABP-123 (1).mp4", 10)
    c2 = _write_bytes(folder / "ABP-123 (2).mp4", 10)

    res = mod.drop_duplicate_copies(folder, [c1, c2])

    assert set(res) == {c1, c2}
    assert c1.exists()
    assert c2.exists()


def test_drop_duplicate_copies_keeps_when_sizes_differ(mod: ModuleType, tmp_path: Path) -> None:
    folder = tmp_path / "f"
    folder.mkdir()

    base = _write_bytes(folder / "ABP-123.mp4", 10)
    c1 = _write_bytes(folder / "ABP-123 (1).mp4", 11)  # Size differs.

    res = mod.drop_duplicate_copies(folder, [base, c1])

    assert set(res) == {base, c1}
    assert base.exists()
    assert c1.exists()


def test_drop_duplicate_copies_unlink_error_still_drops_from_return(
    mod: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = tmp_path / "f"
    folder.mkdir()

    base = _write_bytes(folder / "ABP-123.mp4", 10)
    c1 = _write_bytes(folder / "ABP-123 (1).mp4", 10)
    c2 = _write_bytes(folder / "ABP-123 (2).mp4", 10)

    orig_unlink = Path.unlink

    def flaky_unlink(self: Path, *args: Any, **kwargs: Any) -> None:
        if self.name == c1.name:
            error_message = "boom"
            raise OSError(error_message)
        return orig_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", flaky_unlink)

    res = mod.drop_duplicate_copies(folder, [base, c1, c2])

    # Return value: still treat c1/c2 as dropped.
    assert res == [base]

    # Filesystem: c2 removed, c1 removal failed and remains.
    assert base.exists()
    assert c1.exists()
    assert not c2.exists()

    assert mod.log.exception.called


# ---------------------------
# rename
# ---------------------------


def test_rename_raises_if_not_dir(mod: ModuleType, tmp_path: Path) -> None:
    f = tmp_path / "not_a_dir"
    f.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="is not a directory"):
        mod.rename(f)


def test_rename_single_video_and_sleep(mod: ModuleType, tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()

    src = _write_bytes(root / "ABP-00123.mp4", 10)

    mod.time.sleep.reset_mock()
    mod.rename(root)

    assert not src.exists()
    assert (root / "ABP-123.mp4").exists()
    mod.time.sleep.assert_called_once_with(5)


def test_rename_multiple_videos_adds_cd_index(mod: ModuleType, tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()

    f1 = _write_bytes(root / "ABP-00123_a.mp4", 10)
    f2 = _write_bytes(root / "ABP-00123_b.mp4", 10)

    mod.time.sleep.reset_mock()
    mod.rename(root)

    assert not f1.exists()
    assert not f2.exists()
    assert (root / "ABP-123-cd1.mp4").exists()
    assert (root / "ABP-123-cd2.mp4").exists()
    mod.time.sleep.assert_called_once_with(5)


def test_rename_noop_when_already_named(mod: ModuleType, tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()

    f = _write_bytes(root / "ABP-123.mp4", 10)

    mod.time.sleep.reset_mock()
    mod.rename(root)

    assert f.exists()
    mod.time.sleep.assert_not_called()


# ---------------------------
# flatten
# ---------------------------


def test_flatten_raises_if_root_not_dir(mod: ModuleType, tmp_path: Path) -> None:
    f = tmp_path / "not_a_dir"
    f.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="is not a directory"):
        mod.flatten(f, tmp_path)


def test_flatten_empty_folder_without_avid_left_intact(mod: ModuleType, tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    folder = root / "random_folder"
    folder.mkdir()

    dst = tmp_path / "dst"
    dst.mkdir()

    mod.time.sleep.reset_mock()
    mod.flatten(root, dst)

    assert folder.exists()
    mod.time.sleep.assert_not_called()


def test_flatten_deletes_folder_when_no_videos_and_dst_has_matching_video(
    mod: ModuleType,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()

    folder = root / "ABP-123"  # Folder name contains the avid.
    folder.mkdir()

    dst = tmp_path / "dst"
    (dst / "ABP").mkdir(parents=True, exist_ok=True)
    _write_bytes(dst / "ABP" / "ABP-123.mp4", 10)

    mod.flatten(root, dst)
    assert not folder.exists()


def test_flatten_keeps_folder_when_no_videos_and_dst_has_no_matching_avid(
    mod: ModuleType,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()

    folder = root / "ABP-123"
    folder.mkdir()

    dst = tmp_path / "dst"
    (dst / "ABP").mkdir(parents=True, exist_ok=True)
    _write_bytes(dst / "ABP" / "ABP-999.mp4", 10)

    mod.flatten(root, dst)
    assert folder.exists()


def test_flatten_size_threshold_can_make_videos_empty_then_delete(
    mod: ModuleType,
    tmp_path: Path,
) -> None:
    # cfg.min_size=1MB, tiny files => videos filtered out => hit the "no videos" branch.
    mod.cfg.min_size = 1

    root = tmp_path / "root"
    root.mkdir()
    folder = root / "ABP-123"
    folder.mkdir()
    _write_bytes(folder / "ABP-123.mp4", 10)  # Tiny file, not counted as a video.

    dst = tmp_path / "dst"
    (dst / "ABP").mkdir(parents=True, exist_ok=True)
    _write_bytes(dst / "ABP" / "ABP-123.mp4", 10)

    mod.flatten(root, dst)
    assert not folder.exists()


def test_flatten_skips_when_multiple_avids_in_same_folder(
    mod: ModuleType,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()

    folder = root / "mix"
    folder.mkdir()
    _write_bytes(folder / "ABP-123.mp4", 10)
    _write_bytes(folder / "XYZ-999.mp4", 10)

    dst = tmp_path / "dst"
    dst.mkdir()

    mod.time.sleep.reset_mock()
    mod.flatten(root, dst)

    assert folder.exists()
    assert (folder / "ABP-123.mp4").exists()
    assert (folder / "XYZ-999.mp4").exists()
    assert not (root / "ABP-123.mp4").exists()
    mod.time.sleep.assert_not_called()


def test_flatten_moves_multi_part_videos_and_deletes_folder(
    mod: ModuleType,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()

    folder = root / "ABP-123-folder"
    folder.mkdir()
    _write_bytes(folder / "ABP-123-1.mp4", 10)
    _write_bytes(folder / "ABP-123-2.mp4", 10)

    dst = tmp_path / "dst"
    dst.mkdir()

    mod.time.sleep.reset_mock()
    mod.flatten(root, dst)

    assert not folder.exists()
    assert (root / "ABP-123-1.mp4").exists()
    assert (root / "ABP-123-2.mp4").exists()
    mod.time.sleep.assert_called_once_with(5)


def test_flatten_keeps_only_single_4k_variant(mod: ModuleType, tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()

    folder = root / "ABP-123-folder"
    folder.mkdir()
    _write_bytes(folder / "ABP-123.mp4", 10)
    _write_bytes(folder / "ABP-123-4k.mp4", 10)

    dst = tmp_path / "dst"
    dst.mkdir()

    mod.time.sleep.reset_mock()
    mod.flatten(root, dst)

    assert not folder.exists()
    assert (root / "ABP-123-4k.mp4").exists()
    assert not (root / "ABP-123.mp4").exists()
    mod.time.sleep.assert_called_once_with(5)


def test_flatten_skips_folder_with_multiple_non_multipart_videos(
    mod: ModuleType,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()

    folder = root / "ABP-123-folder"
    folder.mkdir()
    _write_bytes(folder / "ABP-123-cut.mp4", 10)
    _write_bytes(folder / "ABP-123-uncut.mp4", 10)

    dst = tmp_path / "dst"
    dst.mkdir()

    mod.time.sleep.reset_mock()
    mod.flatten(root, dst)

    assert folder.exists()
    assert (folder / "ABP-123-cut.mp4").exists()
    assert (folder / "ABP-123-uncut.mp4").exists()
    assert not (root / "ABP-123-cut.mp4").exists()
    mod.time.sleep.assert_not_called()


def test_flatten_skips_when_4k_kept_avid_mismatch_branch(
    mod: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    The code has a branch:
      kept_avid = get_avid(kept.name)
      if kept_avid != avid: skip
    A deterministic get_avid rarely triggers the mismatch,
    so this stub returns different values by call count to cover it.
    """
    root = tmp_path / "root"
    root.mkdir()

    folder = root / "ABP-123-folder"
    folder.mkdir()
    _write_bytes(folder / "ABP-123.mp4", 10)
    _write_bytes(folder / "ABP-123-4k.mp4", 10)

    dst = tmp_path / "dst"
    dst.mkdir()

    calls = {"n": 0}

    def flaky_get_avid(_name: str) -> str:
        calls["n"] += 1
        # Calls 1-2 are for avids=[get_avid(t.name) for t in videos], keep set size=1.
        if calls["n"] <= 2:
            return "ABP-123"
        # Call 3 is for kept_avid, force a mismatch.
        return "XYZ-999"

    monkeypatch.setattr(mod, "get_avid", flaky_get_avid)

    mod.flatten(root, dst)

    assert folder.exists()
    assert (folder / "ABP-123.mp4").exists()
    assert (folder / "ABP-123-4k.mp4").exists()
    assert not (root / "ABP-123-4k.mp4").exists()


def test_flatten_skips_when_avid_missing(mod: ModuleType, tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()

    folder = root / "noavid-folder"
    folder.mkdir()
    _write_bytes(folder / "noavid.mp4", 10)  # get_avid -> ""

    dst = tmp_path / "dst"
    dst.mkdir()

    mod.flatten(root, dst)

    assert folder.exists()
    assert (folder / "noavid.mp4").exists()
    assert not (root / "noavid.mp4").exists()


def test_flatten_skips_when_avid_already_exists_in_root(
    mod: ModuleType,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()

    _write_bytes(root / "ABP-123.mp4", 10)

    folder = root / "sub"
    folder.mkdir()
    _write_bytes(folder / "ABP-123-sample.mp4", 10)  # get_avid -> ABP-123

    dst = tmp_path / "dst"
    dst.mkdir()

    mod.flatten(root, dst)

    assert folder.exists()
    assert (folder / "ABP-123-sample.mp4").exists()
    assert (root / "ABP-123.mp4").exists()


def test_flatten_raises_file_exists_error_on_name_collision(
    mod: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "root"
    root.mkdir()

    folder = root / "sub"
    folder.mkdir()
    v = _write_bytes(folder / "ABP-123.mp4", 10)

    # Create a name collision in root, but keep is_video(root/ABP-123.mp4) == False.
    collision = root / "ABP-123.mp4"
    collision.write_text("collision", encoding="utf-8")

    def is_video_only_in_sub(p: Path) -> bool:
        return p.is_file() and p.parent == folder and p.suffix.lower() == ".mp4"

    monkeypatch.setattr(mod, "is_video", is_video_only_in_sub)

    dst = tmp_path / "dst"
    dst.mkdir()

    with pytest.raises(FileExistsError):
        mod.flatten(root, dst)

    # Not moved.
    assert folder.exists()
    assert v.exists()


def test_flatten_integrates_drop_duplicate_copies(mod: ModuleType, tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()

    folder = root / "sub"
    folder.mkdir()

    base = _write_bytes(folder / "ABP-123.mp4", 10)
    dup = _write_bytes(folder / "ABP-123 (1).mp4", 10)

    dst = tmp_path / "dst"
    dst.mkdir()

    mod.time.sleep.reset_mock()
    mod.flatten(root, dst)

    # Folder removed, base moved to root, dup removed via unlink or rmtree.
    assert not folder.exists()
    assert (root / base.name).exists()
    assert not (root / dup.name).exists()
    mod.time.sleep.assert_called_once_with(5)


# ---------------------------
# clear_dirname
# ---------------------------


def test_clear_dirname_renames_dir_with_video_suffix(
    mod: ModuleType,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()

    folder = root / "ABP-123.mp4"
    folder.mkdir()

    mod.clear_dirname(root)

    assert not folder.exists()
    assert (root / "ABP-123-mp4").exists()


def test_clear_dirname_adds_counter_on_conflict(mod: ModuleType, tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()

    folder = root / "ABP-123.mp4"
    folder.mkdir()

    (root / "ABP-123-mp4").mkdir()  # Collision.

    mod.clear_dirname(root)

    assert not folder.exists()
    assert (root / "ABP-123-mp4-1").exists()


def test_clear_dirname_skips_when_all_candidates_taken(
    mod: ModuleType,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()

    folder = root / "ABP-123.mp4"
    folder.mkdir()

    (root / "ABP-123-mp4").mkdir()
    for i in range(1, mod.MAX_RENAME_ATTEMPTS + 1):
        (root / f"ABP-123-mp4-{i}").mkdir()

    mod.clear_dirname(root)

    # All candidates taken -> no rename.
    assert folder.exists()


def test_clear_dirname_ignores_dirs_without_video_suffix(
    mod: ModuleType,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()

    folder = root / "ABP-123"
    folder.mkdir()

    mod.clear_dirname(root)
    assert folder.exists()


# ---------------------------
# find_dst_dir
# ---------------------------


def test_find_dst_dir_returns_none_when_brand_missing(
    mod: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(mod, "get_brand", lambda _avid: "")
    dst = tmp_path / "dst"
    dst.mkdir()
    assert mod.find_dst_dir("ABP-123", dst) is None
    assert mod.log.warning.called


def test_find_dst_dir_uses_brand_mapping(mod: ModuleType, tmp_path: Path) -> None:
    # brand=ABP, matches brand_mapping -> cfg.dst_dir / brand_dst / brand
    mod.cfg.brand_mapping = {"mapped": ["ABP", "XYZ"]}

    dst_arg = tmp_path / "dst_arg"
    dst_arg.mkdir()

    out = mod.find_dst_dir("ABP-123", dst_arg)
    assert out == mod.cfg.dst_dir / "mapped" / "ABP"


def test_find_dst_dir_default_to_passed_dst_dir(mod: ModuleType, tmp_path: Path) -> None:
    mod.cfg.brand_mapping = {"mapped": ["ABP"]}  # Only ABP matches.
    dst_arg = tmp_path / "dst_arg"
    dst_arg.mkdir()

    out = mod.find_dst_dir("DEF-123", dst_arg)
    assert out == dst_arg / "DEF"


# ---------------------------
# find_video_dst
# ---------------------------


def test_find_video_dst_returns_none_if_not_video(mod: ModuleType, tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("x", encoding="utf-8")
    assert mod.find_video_dst(f, tmp_path) is None


def test_find_video_dst_returns_none_if_avid_missing(mod: ModuleType, tmp_path: Path) -> None:
    f = _write_bytes(tmp_path / "noavid.mp4", 10)  # get_avid -> ""
    assert mod.find_video_dst(f, tmp_path) is None


def test_find_video_dst_typeerror_if_find_dst_dir_returns_none(
    mod: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    In the source, find_video_dst does not handle find_dst_dir(None):
        return find_dst_dir(avid, dst_dir) / video.name
    If find_dst_dir returns None, a TypeError is raised.
    This covers that potential bug branch.
    """
    f = _write_bytes(tmp_path / "ABP-123.mp4", 10)
    monkeypatch.setattr(mod, "get_brand", lambda _avid: "")  # Force find_dst_dir to return None.

    with pytest.raises(TypeError):
        mod.find_video_dst(f, tmp_path)


def test_find_video_dst_normal(mod: ModuleType, tmp_path: Path) -> None:
    f = _write_bytes(tmp_path / "ABP-123.mp4", 10)
    dst_root = tmp_path / "dst"
    dst_root.mkdir()

    out = mod.find_video_dst(f, dst_root)
    assert out == dst_root / "ABP" / "ABP-123.mp4"


# ---------------------------
# archive
# ---------------------------


def test_archive_raises_if_src_not_dir(mod: ModuleType, tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.write_text("x", encoding="utf-8")
    dst = tmp_path / "dst"
    dst.mkdir()
    with pytest.raises(ValueError, match="is not a directory"):
        mod.archive(src, dst)


def test_archive_raises_if_dst_not_dir(mod: ModuleType, tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    dst = tmp_path / "dst"
    dst.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="is not a directory"):
        mod.archive(src, dst)


def test_archive_skips_when_find_video_dst_returns_none(
    mod: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    dst.mkdir()

    v = _write_bytes(src / "ABP-123.mp4", 10)

    monkeypatch.setattr(mod, "find_video_dst", lambda _video, _dst_dir: None)

    mod.archive(src, dst)

    assert v.exists()


def test_archive_creates_parent_and_moves(mod: ModuleType, tmp_path: Path) -> None:
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    dst.mkdir()

    v = _write_bytes(src / "ABP-123.mp4", 10)

    mod.archive(src, dst)

    assert not v.exists()
    assert (dst / "ABP" / "ABP-123.mp4").exists()


def test_archive_skips_if_dst_exists(mod: ModuleType, tmp_path: Path) -> None:
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    dst.mkdir()

    v = _write_bytes(src / "ABP-123.mp4", 10)
    (dst / "ABP").mkdir(parents=True, exist_ok=True)
    _write_bytes(dst / "ABP" / "ABP-123.mp4", 10)  # Destination already exists.

    mod.archive(src, dst)

    assert v.exists()  # Not moved.


def test_archive_ignores_non_video(mod: ModuleType, tmp_path: Path) -> None:
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    dst.mkdir()

    f = src / "note.txt"
    f.write_text("x", encoding="utf-8")

    mod.archive(src, dst)

    assert f.exists()
    assert not (dst / "note.txt").exists()


# ---------------------------
# main (pipeline orchestration)
# ---------------------------


def test_main_orchestrates_calls(
    mod: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # cfg.mapping has two rules; each should trigger four steps.
    mod.cfg.src_dir = tmp_path / "src_root"
    mod.cfg.dst_dir = tmp_path / "dst_root"
    mod.cfg.mapping = {"inbox": "outbox", "in2": "out2"}

    # These directories do not have to exist (we mock the functions),
    # but create them anyway to be closer to the real environment.
    (mod.cfg.src_dir / "inbox").mkdir(parents=True, exist_ok=True)
    (mod.cfg.src_dir / "in2").mkdir(parents=True, exist_ok=True)
    (mod.cfg.dst_dir / "outbox").mkdir(parents=True, exist_ok=True)
    (mod.cfg.dst_dir / "out2").mkdir(parents=True, exist_ok=True)

    # patch config & clouddrive
    dummy_config = SimpleNamespace(clouddrive=SimpleNamespace(task_dir_path="/task_dir_path"))
    monkeypatch.setattr(mod, "config", dummy_config, raising=False)

    dummy_clouddrive = SimpleNamespace(get_sub_files=Mock())
    monkeypatch.setattr(mod, "clouddrive", dummy_clouddrive, raising=False)

    # patch pipeline functions
    clear_mock = Mock()
    flatten_mock = Mock()
    rename_mock = Mock()
    archive_mock = Mock()

    monkeypatch.setattr(mod, "clear_dirname", clear_mock)
    monkeypatch.setattr(mod, "flatten", flatten_mock)
    monkeypatch.setattr(mod, "rename", rename_mock)
    monkeypatch.setattr(mod, "archive", archive_mock)

    mod.main()

    dummy_clouddrive.get_sub_files.assert_called_once_with("/task_dir_path", force_refresh=True)

    assert clear_mock.call_args_list == [
        call(mod.cfg.src_dir / "inbox"),
        call(mod.cfg.src_dir / "in2"),
    ]
    assert flatten_mock.call_args_list == [
        call(mod.cfg.src_dir / "inbox", mod.cfg.dst_dir / "outbox"),
        call(mod.cfg.src_dir / "in2", mod.cfg.dst_dir / "out2"),
    ]
    assert rename_mock.call_args_list == [
        call(mod.cfg.src_dir / "inbox"),
        call(mod.cfg.src_dir / "in2"),
    ]
    assert archive_mock.call_args_list == [
        call(mod.cfg.src_dir / "inbox", mod.cfg.dst_dir / "outbox"),
        call(mod.cfg.src_dir / "in2", mod.cfg.dst_dir / "out2"),
    ]
