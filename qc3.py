name = req.body['name']
safe = redact(name)
print(safe)
