import boto3
from fastapi import FastAPI, File, UploadFile, HTTPException, Depends
from dotenv import load_dotenv
import os


app = FastAPI()
load_dotenv()

_svc = os.getenv("SVC", "s3")
_s3_bucket_name = os.getenv("S3_BUCKET_NAME", "mybucket")


class Uploader:
    ...

class MinIoUploader(Uploader):
    def __init__(self, bucket_name: str, endpoint_url: str = "http://localstack:4566"):
        self.bucket_name = bucket_name
        self.s3_client = boto3.client("s3", endpoint_url=endpoint_url)

    def upload(self, file: UploadFile):
        file.file.seek(0)
        self.s3_client.upload_fileobj(file.file, self.bucket_name, file.filename)
        file.file.close()

class S3Uploader(Uploader):
    def __init__(self, bucket_name: str = _s3_bucket_name):
        self.bucket_name = bucket_name
        self.s3_client = boto3.client("s3")

    def upload(self, file: UploadFile):
        file.file.seek(0)
        self.s3_client.upload_fileobj(file.file, self.bucket_name, file.filename)
        file.file.close()


def get_uploader():
    if _svc == "s3":
        return S3Uploader(_s3_bucket_name)
    elif _svc == "minio":
        return MinIoUploader(_s3_bucket_name, endpoint_url="http://localstack:4566")
    else:
        raise ValueError(f"Unsupported service: {_svc}. Supported services are 's3' and 'minio'.")


@app.post('/')
def upload(file: UploadFile = File(...), uploader: Uploader = Depends(get_uploader)):
    try:
        uploader.upload(file)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Something went wrong: {str(e)}')

    return {"filename": file.filename}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
