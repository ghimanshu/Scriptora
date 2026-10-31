from app.core.config import get_settings


class LocalStorage:
    def __init__(self):
        self.root = get_settings().local_storage_root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key):
        target = (self.root / key).resolve()
        if not target.is_relative_to(self.root) or target == self.root:
            raise ValueError("Invalid storage key")
        return target

    def put(self, key, data):
        with self.path(key).open("xb") as stream:
            stream.write(data)

    def get(self, key):
        return self.path(key).read_bytes()


class S3Storage:
    def __init__(self):
        import boto3

        cfg = get_settings()
        self.bucket = cfg.object_storage_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=cfg.object_storage_endpoint or None,
            region_name=cfg.object_storage_region or None,
        )

    def put(self, key, data):
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ServerSideEncryption="AES256",
            IfNoneMatch="*",
            ContentType="application/octet-stream",
        )

    def get(self, key):
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()


def storage():
    return LocalStorage() if get_settings().storage_driver == "local" else S3Storage()
