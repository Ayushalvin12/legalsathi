import psycopg2
from contextlib import contextmanager
from dotenv import load_dotenv
import os

load_dotenv()


 # Debug line


def connect_db():
    try:
        conn = psycopg2.connect(
            dbname=os.getenv("DB_NAME", "legalsathi"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "superuser"),
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5432")
        )
        print("Connection successful....Type: {type(conn)}")
        return conn
    except Exception as e:
        raise Exception(f"DB connection Failed: {e}")

@contextmanager
def get_db_cursor():
    conn = connect_db()
    if conn is None:
        raise Exception("Database connection failed")
    cursor = conn.cursor()
    try:
        yield cursor
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()