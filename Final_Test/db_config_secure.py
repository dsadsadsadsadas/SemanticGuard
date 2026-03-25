# Secure Database Configuration
import os
import psycopg2
from typing import Optional

def get_connection():
    """Get database connection with credentials from environment"""
    db_host = os.getenv('DB_HOST')
    db_user = os.getenv('DB_USER')
    db_password = os.getenv('DB_PASSWORD')
    db_name = os.getenv('DB_NAME')
    
    if not all([db_host, db_user, db_password, db_name]):
        raise ValueError("Database credentials not found in environment")
    
    return psycopg2.connect(
        host=db_host,
        user=db_user,
        password=db_password,
        database=db_name
    )
