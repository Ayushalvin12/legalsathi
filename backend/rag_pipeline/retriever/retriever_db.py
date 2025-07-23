import os
import psycopg2

def connect_db():
    try:
        conn = psycopg2.connect(
            dbname=os.getenv("DB_NAME", "legalsathi"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "superuser"),
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5432")
        )
        print(f"Connection successful....")
        return conn

    except Exception as e:
        print(f"Error: {e}")
        return None

# === Get or Create User ===
def get_or_create_user(conn, name="default_user"):
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM users WHERE name=%s", (name,))
        user = cur.fetchone()
        if user:
            return user[0]
        
        dummy_email = f"{name}@example.com"
        default_role = "client"
        access_token = ""
        refresh_token = ""
        cur.execute("""
            INSERT INTO users (name, email) 
            VALUES (%s, %s) 
            RETURNING id
        """, (name, dummy_email))
        user_id = cur.fetchone()[0]
        conn.commit()
        return user_id

# === Create New Conversation ===
def create_conversation(conn, user_id):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO conversations (user_id, created_at) VALUES (%s, NOW()) RETURNING id",
            (user_id,)
        )
        conv_id = cur.fetchone()[0]
        conn.commit()
        return conv_id

# === Insert Message ===
def insert_message(conn, conversation_id, role, content):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (%s, %s, %s, NOW())",
            (conversation_id, role, content)
        )
        conn.commit()

if __name__=="__main__":
    connect_db()