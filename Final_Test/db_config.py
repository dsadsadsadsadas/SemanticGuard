# Database Configuration
DB_HOST = "prod-db.example.com"
DB_USER = "admin"
DB_PASSWORD = "SuperSecret123!"
DB_NAME = "production_db"

def get_connection():
    import psycopg2
    return psycopg2.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )
