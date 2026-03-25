# Secure Search Service
import sqlite3
from typing import List, Tuple

def search_products(query: str) -> List[Tuple]:
    """Search products with parameterized query"""
    conn = sqlite3.connect('products.db')
    cursor = conn.cursor()
    
    # SECURE: Parameterized query prevents SQL injection
    sql = "SELECT * FROM products WHERE name LIKE ?"
    cursor.execute(sql, (f'%{query}%',))
    results = cursor.fetchall()
    conn.close()
    
    return results
