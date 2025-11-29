import grpc
from google.protobuf import empty_pb2

from src.core import config

from . import clouddrive_pb2, clouddrive_pb2_grpc


class CloudDriveClient:
    def __init__(self) -> None:
        """初始化 CloudDrive 客户端

        Args:
            address: 服务器地址 (例如 'localhost:19798')
        """
        self.channel = grpc.secure_channel(config.clouddrive.address, grpc.ssl_channel_credentials())
        self.stub = clouddrive_pb2_grpc.CloudDriveFileSrvStub(self.channel)

    def close(self) -> None:
        """关闭通道"""
        self.channel.close()

    def _create_authorized_metadata(self) -> list[tuple[str, str]]:
        """创建带授权头的元数据"""
        return [('authorization', f'Bearer {config.clouddrive.api_token}')]

    def get_system_info(self) -> clouddrive_pb2.CloudDriveSystemInfo:
        """获取系统信息(无需认证)

        Returns:
            CloudDriveSystemInfo: 系统信息
        """
        return self.stub.GetSystemInfo(empty_pb2.Empty())

    def get_sub_files(self, path: str, force_refresh: bool = False) -> list[clouddrive_pb2.CloudDriveFile]:
        """列出目录中的文件

        Args:
            path: 目录路径
            force_refresh: 强制刷新缓存

        Returns:
            list: CloudDriveFile 对象列表
        """
        request = clouddrive_pb2.ListSubFileRequest(
            path=path,
            forceRefresh=force_refresh,
        )

        metadata = self._create_authorized_metadata()
        files = []

        for response in self.stub.GetSubFiles(request, metadata=metadata):
            files.extend(response.subFiles)

        return files

    def create_folder(self, parent_path: str, folder_name: str) -> clouddrive_pb2.CreateFolderResult:
        """创建新文件夹

        Args:
            parent_path: 父目录路径
            folder_name: 新文件夹名称

        Returns:
            CreateFolderResult: 操作结果
        """
        request = clouddrive_pb2.CreateFolderRequest(
            parentPath=parent_path,
            folderName=folder_name,
        )

        metadata = self._create_authorized_metadata()
        return self.stub.CreateFolder(request, metadata=metadata)

    def delete_file(self, file_path: str) -> clouddrive_pb2.FileOperationResult:
        """删除文件或文件夹

        Args:
            file_path: 文件或文件夹路径

        Returns:
            FileOperationResult: 操作结果
        """
        request = clouddrive_pb2.FileRequest(path=file_path)
        metadata = self._create_authorized_metadata()
        return self.stub.DeleteFile(request, metadata=metadata)

    def rename_file(self, file_path: str, new_name: str) -> clouddrive_pb2.FileOperationResult:
        """重命名文件

        Args:
            file_path: 当前文件路径
            new_name: 新文件名

        Returns:
            FileOperationResult: 操作结果
        """
        request = clouddrive_pb2.RenameFileRequest(
            theFilePath=file_path,
            newName=new_name,
        )

        metadata = self._create_authorized_metadata()
        return self.stub.RenameFile(request, metadata=metadata)

    def move_file(self, source_paths: list[str], dest_path: str, conflict_policy: int = 0) -> clouddrive_pb2.FileOperationResult:
        """移动文件到目标位置

        Args:
            source_paths: 源文件路径列表
            dest_path: 目标路径
            conflict_policy: 0=覆盖, 1=重命名, 2=跳过

        Returns:
            FileOperationResult: 操作结果
        """
        request = clouddrive_pb2.MoveFileRequest(
            theFilePaths=source_paths,
            destPath=dest_path,
            conflictPolicy=conflict_policy,
        )

        metadata = self._create_authorized_metadata()
        return self.stub.MoveFile(request, metadata=metadata)

    def add_offline_file(self, urls: str | list[str], dst_dir: str) -> clouddrive_pb2.FileOperationResult:
        """添加离线文件
        Args:
            urls: 文件URL列表
            to_folder: 目标文件夹
        """
        if isinstance(urls, str):
            urls = [urls]
        urls = '\n'.join(urls)
        request = clouddrive_pb2.AddOfflineFileRequest(
            urls=urls,
            toFolder=dst_dir,
            checkFolderAfterSecs=3,
        )
        metadata = self._create_authorized_metadata()
        return self.stub.AddOfflineFiles(request, metadata=metadata)


clouddrive = CloudDriveClient()
