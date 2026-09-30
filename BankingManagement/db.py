import mysql.connector

def get_db_connection():

    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="Ramya@1610",
            database="bank_management_system"
        )

        return conn

    except mysql.connector.Error as err:
        print("Database Connection Error:", err)
        return None