import psycopg2
from contextlib import contextmanager
from dotenv import load_dotenv
import os

load_dotenv()

def connect_db():
    try:
        conn = psycopg2.connect(
            dbname="legalsathi",
            user="postgres",
            password=os.getenv("DATABASE_PASSWORD"),
            host="localhost",
            port="5432"
        )
        print("Connection successful....")
        return conn
    except Exception as e:
        print(f"Error: {e}")
        return None

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