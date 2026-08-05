import psycopg2
import bcrypt

# SELECT *
# FROM public.users
# WHERE full_name ILIKE '%Kgomotso S%';

# role
# "SUPER_ADMIN"
# "REVIEWER"
# "SUPERVISOR"
# "ADMIN"
# "STUDENT"

# passwords changed
# student
# email = 225174817@student.uj.ac.za
# password = 219050918@Rash

# Reviewer
# USER_EMAIL :acbawa@gmail.com
# Password: 219050918@Rash

# Supervisor
# Email:ugochukwu.albert@gmail.com
# Password: 219050918@Rash

# Admin
# Email:kabelo.mokoena@uj.ac.za
# Password: 219050918@Rash

# Supervisor
# Email: thabiled@uj.ac.za
# Password: 219050918@Rash

# Reviewer
# USER_EMAIL = "lynnvr@uj.ac.za"
# NEW_PASSWORD = "219050918@Rash"

# Reviewer
# USER_EMAIL = "ntswakim@uj.ac.za"
# NEW_PASSWORD = "219050918@Rash"


# ============================================================
# CHANGE THESE TWO VALUES ONLY
# ============================================================
USER_EMAIL = "mmunsamy@uj.ac.za"
NEW_PASSWORD = "mmunsamy@uj.ac.za"
# ============================================================


def get_db_connection():
    try:
        conn = psycopg2.connect(
            dbname="INTEGRATED_ETHICS_AND_MBA_FINAL",
            user="postgres",
            password="219050918@Rajour",
            host="localhost",
            port="5432"
        )
        return conn
    except Exception as e:
        print("Error connecting to PostgreSQL database:", e)
        return None


def make_bcrypt_hash(password):
    """
    Creates a bcrypt hash in the format your login verifier expects.
    Example output starts with: $2b$12$
    """
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)
    hashed_password = bcrypt.hashpw(password_bytes, salt)
    return hashed_password.decode("utf-8")


def update_user_password(email, new_password):
    if not email or not new_password:
        print("Email and password are required.")
        return False

    conn = get_db_connection()

    if conn is None:
        print("Database connection failed.")
        return False

    cursor = None

    try:
        cursor = conn.cursor()

        email = email.strip().lower()
        new_password = new_password.strip()

        hashed_password = make_bcrypt_hash(new_password)

        # Test locally before saving
        test_ok = bcrypt.checkpw(
            new_password.encode("utf-8"),
            hashed_password.encode("utf-8")
        )

        if not test_ok:
            print("Generated hash failed local verification.")
            return False

        update_query = """
            UPDATE public.users
            SET password = %s
            WHERE LOWER(TRIM(email)) = LOWER(TRIM(%s))
            RETURNING user_id, full_name, email, password, authenticate_student;
        """

        cursor.execute(update_query, (hashed_password, email))
        updated_user = cursor.fetchone()

        if not updated_user:
            conn.rollback()
            print(f"No user found with email: {email}")
            return False

        conn.commit()

        user_id, full_name, user_email, saved_hash, authenticate_student = updated_user

        print("Password updated successfully.")
        print(f"User ID: {user_id}")
        print(f"Full Name: {full_name}")
        print(f"Email: {user_email}")
        print(f"Authenticate Student: {authenticate_student}")
        print(f"Saved Hash Starts With: {saved_hash[:7]}")
        print("")
        print("Use this exact password to login:")
        print(new_password)

        return True

    except Exception as e:
        conn.rollback()
        print("Error updating password:", e)
        return False

    finally:
        if cursor:
            cursor.close()
        conn.close()


if __name__ == "__main__":
    update_user_password(USER_EMAIL, NEW_PASSWORD)