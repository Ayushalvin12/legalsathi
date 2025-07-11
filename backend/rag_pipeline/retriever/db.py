import psycopg2

def connect_db():
    try:
        conn = psycopg2.connect(
            dbname="legalsathi",
            user="postgres",
            password="",
            host="localhost",
            port="5432"
        )
        print(f"Connection successful....")
        return conn

    except Exception as e:
        print(f"Error: {e}")

# === Get or Create User ===
def get_or_create_user(conn, username="default_user"):
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM users WHERE username=%s", (username,))
        user = cur.fetchone()
        if user:
            return user[0]
        
        dummy_email = f"{username}@example.com"
        cur.execute("""
            INSERT INTO users (username, email) 
            VALUES (%s, %s) 
            RETURNING id
        """, (username, dummy_email))
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