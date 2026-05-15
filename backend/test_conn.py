import os
import psycopg2
from dotenv import load_dotenv

def test_connection():
    load_dotenv()
    url = os.environ.get("POSTGRES_URL")
    if not url:
        print("POSTGRES_URL is not set in environment or .env file")
        return
        
    try:
        print(f"Attempting to connect...")
        conn = psycopg2.connect(url, connect_timeout=10)
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        print(f"Successfully connected to PostgreSQL!")
        print(f"Database version: {version[0]}")
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Failed to connect: {e}")

if __name__ == "__main__":
    test_connection()
