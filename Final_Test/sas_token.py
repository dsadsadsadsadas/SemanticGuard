def upload_to_blob(data):
    # VULNERABLE: Hardcoded Azure SAS storage token in source code
    sas_token = "?sv=2022-11-02&ss=bfqt&srt=sco&sp=rwdlacupiytfx&se=2026-06-03T18:30:00Z&st=2024-06-03T10:30:00Z&spr=https&sig=vulnerableSignatureKey123"
    blob_client = get_client(sas_token)
    blob_client.upload(data)
