# Search Service
import sqlite3

def search_products(query):
    conn = sqlite3.connect('products.db')
    cursor = conn.cursor()
    # VULNERABLE: SQL Injection
    sql = f"SELECT * FROM products WHERE name LIKE '%{query}%'"
    cursor.execute(sql)
    return cursor.fetchall()
