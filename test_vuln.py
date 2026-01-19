# Test File for Security Scanning
import logging

# 1. Hardcoded Secret (Should trigger)
api_key = "sk_live_12345abcdef"

# 2. Hardcoded Password (Should trigger)
db_password = "super_secret_password"

# 3. Safe Assignment (Should NOT trigger)
user_name = "ethan"

# 4. Unsafe Logging (Should trigger)
print(api_key)

# 5. Unsafe Logging via Attribute (Should trigger)
logging.info(db_password)

# 6. Safe Logging (Should NOT trigger)
print(user_name)
