import importlib
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


def test_clouddrive_calls_include_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    clouddrive_module = importlib.import_module('src.utils.clouddrive.clouddrive')
    channel = SimpleNamespace(close=Mock())
    finished_result = clouddrive_module.clouddrive_pb2.OfflineFileListResult()
    stub = SimpleNamespace(
        GetSystemInfo=Mock(return_value=object()),
        GetSubFiles=Mock(return_value=[]),
        CreateFolder=Mock(return_value=object()),
        DeleteFile=Mock(return_value=object()),
        RenameFile=Mock(return_value=object()),
        MoveFile=Mock(return_value=object()),
        AddOfflineFiles=Mock(return_value=object()),
        ListOfflineFilesByPath=Mock(return_value=finished_result),
        ClearOfflineFiles=Mock(return_value=None),
    )
    monkeypatch.setattr(clouddrive_module.grpc, 'secure_channel', Mock(return_value=channel))
    monkeypatch.setattr(clouddrive_module.clouddrive_pb2_grpc, 'CloudDriveFileSrvStub', Mock(return_value=stub))

    client = clouddrive_module.CloudDriveClient()
    client.get_system_info()
    client.get_sub_files('/media')
    client.create_folder('/media', 'new')
    client.delete_file('/media/old')
    client.rename_file('/media/old', 'new')
    client.move_file(['/media/file'], '/media/dst')
    client.add_offline_file('magnet:?xt=urn:btih:abc', '/media')
    client.list_finished_offline_files_by_path('/media')
    client.clear_finished_offline_files('/media')

    for call in [
        stub.GetSystemInfo,
        stub.GetSubFiles,
        stub.CreateFolder,
        stub.DeleteFile,
        stub.RenameFile,
        stub.MoveFile,
        stub.AddOfflineFiles,
        stub.ListOfflineFilesByPath,
        stub.ClearOfflineFiles,
    ]:
        assert call.call_args.kwargs['timeout'] == clouddrive_module.GRPC_TIMEOUT_SECONDS
