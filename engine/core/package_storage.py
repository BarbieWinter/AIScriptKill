"""私有存储剧本包归档并返回不透明的存储定位符。"""

import asyncio
from dataclasses import dataclass, field

from engine.api.config import get_settings
from engine.core.package_schema import PackageAssetRecord
from supabase import Client, create_client


@dataclass(slots=True)
class SupabasePackageAssetStorage:
    """将剧本包资源上传到使用前已强制设为私有的存储桶。"""

    client: Client
    bucket: str
    _bucket_checked: bool = field(default=False, init=False)

    async def upload_asset(self, package_id: str, asset: PackageAssetRecord) -> str:
        """在事件循环外上传资源并返回其私有定位符。"""

        return await asyncio.to_thread(self._upload_asset, package_id, asset)

    def _upload_asset(self, package_id: str, asset: PackageAssetRecord) -> str:
        self._ensure_bucket()
        object_path = f"{package_id}/{asset.path}"
        self.client.storage.from_(self.bucket).upload(
            object_path,
            asset.content,
            {
                "cache-control": "3600",
                "content-type": asset.content_type,
                "upsert": "true",
            },
        )
        return f"storage://{self.bucket}/{object_path}"

    def _ensure_bucket(self) -> None:
        if self._bucket_checked:
            return
        if self._bucket_exists():
            self.client.storage.update_bucket(
                self.bucket,
                options={"public": False},
            )
        else:
            self.client.storage.create_bucket(
                self.bucket,
                options={"public": False},
            )
        self._bucket_checked = True

    def _bucket_exists(self) -> bool:
        for bucket in self.client.storage.list_buckets():
            if getattr(bucket, "id", None) == self.bucket:
                return True
            if getattr(bucket, "name", None) == self.bucket:
                return True
        return False


def create_package_asset_storage() -> SupabasePackageAssetStorage:
    """根据已校验的 Supabase 配置构建私有剧本包存储。"""

    settings = get_settings()
    return SupabasePackageAssetStorage(
        client=create_client(settings.supabase_url, settings.supabase_secret_key),
        bucket=settings.supabase_storage_bucket,
    )
