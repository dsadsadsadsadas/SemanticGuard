import os
def upload_to_blob(data):
    # SAFE: Retrieving SAS token from secure environment variables
    sas_token = os.getenv('AZURE_STORAGE_SAS_TOKEN')
    blob_client = get_client(sas_token)
    blob_client.upload(data)
