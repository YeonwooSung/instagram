import boto3
from fastapi import FastAPI, File, UploadFile, HTTPException


app = FastAPI()

@app.post('/')
def upload(file: UploadFile = File(...)):
    try:
        s3_client = boto3.client("s3", endpoint_url="http://localstack:4566")

        contents = file.file.read()
        file.file.seek(0)
        # Upload the file to to your S3 service
        s3_client.upload_fileobj(file.file, 'local', 'myfile.txt')
    except Exception:
        raise HTTPException(status_code=500, detail='Something went wrong')
    finally:
        file.file.close()

    print(contents)  # Handle file contents as desired
    return {"filename": file.filename}
