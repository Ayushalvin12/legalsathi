import psycopg2
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
