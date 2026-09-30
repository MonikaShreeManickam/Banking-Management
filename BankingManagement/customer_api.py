# =========================================================
# SECURE BANK - CUSTOMER REST API
# =========================================================

from flask import Blueprint, request, jsonify, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from db import get_db_connection

import random
import re


# =========================================================
# BLUEPRINT
# =========================================================

customer_api = Blueprint(
    "customer_api",
    __name__,
    url_prefix="/api/customer"
)


# =========================================================
# TOKEN SETTINGS
# =========================================================

TOKEN_EXPIRY = 60 * 60 * 24 * 7
# 7 days


def get_serializer():
    """
    Creates a secure signed token serializer.
    Uses Flask SECRET_KEY.
    """

    return URLSafeTimedSerializer(
        current_app.config["SECRET_KEY"],
        salt="secure-bank-customer-api"
    )


def create_token(customer_id):

    serializer = get_serializer()

    token = serializer.dumps({
        "customer_id": int(customer_id)
    })

    return token


def get_customer_id_from_token():

    auth_header = request.headers.get("Authorization", "")

    if not auth_header:
        return None, "Authorization token is required."

    if not auth_header.startswith("Bearer "):
        return None, "Invalid Authorization format."

    token = auth_header[7:].strip()

    if not token:
        return None, "Token is missing."

    serializer = get_serializer()

    try:

        data = serializer.loads(
            token,
            max_age=TOKEN_EXPIRY
        )

        customer_id = data.get("customer_id")

        if not customer_id:
            return None, "Invalid token."

        return int(customer_id), None

    except SignatureExpired:

        return None, "Token expired. Please login again."

    except BadSignature:

        return None, "Invalid token."

    except Exception:

        return None, "Authentication failed."


# =========================================================
# COMMON RESPONSE
# =========================================================

def error_response(message, status=400):

    return jsonify({
        "success": False,
        "message": message
    }), status


def success_response(data=None, message="Success"):

    response = {
        "success": True,
        "message": message
    }

    if data is not None:
        response["data"] = data

    return jsonify(response), 200


# =========================================================
# CUSTOMER LOGIN
# =========================================================

@customer_api.route("/login", methods=["POST"])
def api_login():

    data = request.get_json(silent=True)

    if not data:

        return error_response(
            "JSON request body is required."
        )

    username = str(
        data.get("username", "")
    ).strip()

    password = str(
        data.get("password", "")
    )

    if not username or not password:

        return error_response(
            "Username and password are required."
        )

    conn = None
    cursor = None

    try:

        conn = get_db_connection()

        cursor = conn.cursor(
            dictionary=True
        )

        cursor.execute(
            """
            SELECT *
            FROM customer
            WHERE username=%s
            """,
            (username,)
        )

        customer = cursor.fetchone()

        if not customer:

            return error_response(
                "Invalid Username or Password.",
                401
            )

        stored_password = customer.get(
            "password"
        )

        password_valid = False

        # -------------------------------------------------
        # Check hashed password
        # -------------------------------------------------

        try:

            password_valid = check_password_hash(
                stored_password,
                password
            )

        except Exception:

            password_valid = False

        # -------------------------------------------------
        # Old plain-text password support
        # -------------------------------------------------

        if (
            not password_valid
            and stored_password == password
        ):

            password_valid = True

            new_hash = generate_password_hash(
                password
            )

            cursor.execute(
                """
                UPDATE customer
                SET password=%s
                WHERE customer_id=%s
                """,
                (
                    new_hash,
                    customer["customer_id"]
                )
            )

            conn.commit()

        if not password_valid:

            return error_response(
                "Invalid Username or Password.",
                401
            )

        # -------------------------------------------------
        # Create API token
        # -------------------------------------------------

        token = create_token(
            customer["customer_id"]
        )

        # -------------------------------------------------
        # Get account
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT
                account_number,
                account_type,
                balance,
                ifsc_code,
                branch_name,
                account_status,
                opening_date
            FROM account
            WHERE customer_id=%s
            """,
            (
                customer["customer_id"],
            )
        )

        account = cursor.fetchone()

        return success_response(
            {
                "token": token,

                "customer": {
                    "customer_id":
                        customer["customer_id"],

                    "full_name":
                        customer.get("full_name"),

                    "username":
                        customer.get("username"),

                    "email":
                        customer.get("email"),

                    "mobile":
                        customer.get("mobile")
                },

                "account": account
            },

            "Login successful."
        )

    except Exception as e:

        print(
            "Customer API Login Error:",
            repr(e)
        )

        return error_response(
            "Login failed. Please try again.",
            500
        )

    finally:

        if cursor:
            cursor.close()

        if conn:
            conn.close()


# =========================================================
# CUSTOMER REGISTER
# =========================================================

@customer_api.route("/register", methods=["POST"])
def api_register():

    data = request.get_json(silent=True)

    if not data:

        return error_response(
            "JSON request body is required."
        )

    fullname = str(
        data.get("fullname", "")
    ).strip()

    email = str(
        data.get("email", "")
    ).strip()

    mobile = str(
        data.get("mobile", "")
    ).strip()

    address = str(
        data.get("address", "")
    ).strip()

    aadhaar = str(
        data.get("aadhaar", "")
    ).strip()

    accounttype = str(
        data.get("accounttype", "")
    ).strip()

    dob = str(
        data.get("dob", "")
    ).strip()

    gender = str(
        data.get("gender", "")
    ).strip()

    username = str(
        data.get("username", "")
    ).strip()

    password = str(
        data.get("password", "")
    )

    confirm_password = str(
        data.get("confirmpassword", "")
    )

    # -------------------------------------------------
    # Required fields
    # -------------------------------------------------

    required_fields = {
        "fullname": fullname,
        "email": email,
        "mobile": mobile,
        "address": address,
        "aadhaar": aadhaar,
        "accounttype": accounttype,
        "dob": dob,
        "gender": gender,
        "username": username,
        "password": password,
        "confirmpassword": confirm_password
    }

    for field, value in required_fields.items():

        if not value:

            return error_response(
                f"{field} is required."
            )

    # -------------------------------------------------
    # Password confirmation
    # -------------------------------------------------

    if password != confirm_password:

        return error_response(
            "Password and Confirm Password do not match."
        )

    # -------------------------------------------------
    # Password validation
    # -------------------------------------------------

    pattern = (
        r"^(?=.*[a-z])"
        r"(?=.*[A-Z])"
        r"(?=.*\d)"
        r"(?=.*[@$!%*?&])"
        r".{8,}$"
    )

    if not re.match(
        pattern,
        password
    ):

        return error_response(
            "Password must contain uppercase, "
            "lowercase, number and special character."
        )

    conn = None
    cursor = None

    try:

        conn = get_db_connection()

        cursor = conn.cursor(
            dictionary=True
        )

        # -------------------------------------------------
        # Check username
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT customer_id
            FROM customer
            WHERE username=%s
            """,
            (username,)
        )

        if cursor.fetchone():

            return error_response(
                "Username already exists."
            )

        # -------------------------------------------------
        # Hash password
        # -------------------------------------------------

        password_hash = generate_password_hash(
            password
        )

        # -------------------------------------------------
        # Insert customer
        # -------------------------------------------------

        cursor.execute(
            """
            INSERT INTO customer
            (
                full_name,
                email,
                mobile,
                address,
                date_of_birth,
                gender,
                account_type,
                username,
                password,
                created_date,
                aadhaar
            )
            VALUES
            (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,
                CURDATE(),%s
            )
            """,
            (
                fullname,
                email,
                mobile,
                address,
                dob,
                gender,
                accounttype,
                username,
                password_hash,
                aadhaar
            )
        )

        customer_id = cursor.lastrowid

        # -------------------------------------------------
        # Generate unique 12 digit account number
        # -------------------------------------------------

        while True:

            account_number = random.randint(
                100000000000,
                999999999999
            )

            cursor.execute(
                """
                SELECT account_number
                FROM account
                WHERE account_number=%s
                """,
                (account_number,)
            )

            if cursor.fetchone() is None:

                break

        # -------------------------------------------------
        # Account details
        # -------------------------------------------------

        ifsc_code = "SECU0000001"

        branch_name = "Main Branch"

        # -------------------------------------------------
        # Create account
        # -------------------------------------------------

        cursor.execute(
            """
            INSERT INTO account
            (
                account_number,
                customer_id,
                account_type,
                balance,
                ifsc_code,
                branch_name,
                account_status,
                opening_date
            )
            VALUES
            (
                %s,%s,%s,%s,%s,%s,%s,CURDATE()
            )
            """,
            (
                account_number,
                customer_id,
                accounttype,
                0.00,
                ifsc_code,
                branch_name,
                "Active"
            )
        )

        conn.commit()

        return success_response(
            {
                "customer_id":
                    customer_id,

                "account_number":
                    account_number,

                "username":
                    username
            },

            "Registration successful."
        )

    except Exception as e:

        if conn:
            conn.rollback()

        print(
            "Customer API Registration Error:",
            repr(e)
        )

        return error_response(
            "Registration failed. Please try again.",
            500
        )

    finally:

        if cursor:
            cursor.close()

        if conn:
            conn.close()


# =========================================================
# GET CUSTOMER PROFILE
# =========================================================

@customer_api.route("/profile", methods=["GET"])
def api_profile():

    customer_id, error = get_customer_id_from_token()

    if error:

        return error_response(
            error,
            401
        )

    conn = None
    cursor = None

    try:

        conn = get_db_connection()

        cursor = conn.cursor(
            dictionary=True
        )

        # -------------------------------------------------
        # Customer
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT
                customer_id,
                full_name,
                email,
                mobile,
                address,
                date_of_birth,
                gender,
                account_type,
                username,
                profile_photo,
                created_date,
                aadhaar
            FROM customer
            WHERE customer_id=%s
            """,
            (customer_id,)
        )

        customer = cursor.fetchone()

        if not customer:

            return error_response(
                "Customer not found.",
                404
            )

        # -------------------------------------------------
        # Account
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT
                account_number,
                customer_id,
                account_type,
                balance,
                ifsc_code,
                branch_name,
                account_status,
                opening_date
            FROM account
            WHERE customer_id=%s
            """,
            (customer_id,)
        )

        account = cursor.fetchone()

        return success_response(
            {
                "customer": customer,
                "account": account
            },

            "Profile loaded successfully."
        )

    except Exception as e:

        print(
            "Customer API Profile Error:",
            repr(e)
        )

        return error_response(
            "Unable to load profile.",
            500
        )

    finally:

        if cursor:
            cursor.close()

        if conn:
            conn.close()


# =========================================================
# CUSTOMER DASHBOARD
# =========================================================

@customer_api.route("/dashboard", methods=["GET"])
def api_dashboard():

    customer_id, error = get_customer_id_from_token()

    if error:

        return error_response(
            error,
            401
        )

    conn = None
    cursor = None

    try:

        conn = get_db_connection()

        cursor = conn.cursor(
            dictionary=True
        )

        # -------------------------------------------------
        # Customer
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT
                customer_id,
                full_name,
                username,
                email,
                mobile,
                profile_photo
            FROM customer
            WHERE customer_id=%s
            """,
            (customer_id,)
        )

        customer = cursor.fetchone()

        if not customer:

            return error_response(
                "Customer not found.",
                404
            )

        # -------------------------------------------------
        # Account
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT
                account_number,
                account_type,
                balance,
                ifsc_code,
                branch_name,
                account_status,
                opening_date
            FROM account
            WHERE customer_id=%s
            """,
            (customer_id,)
        )

        account = cursor.fetchone()

        # -------------------------------------------------
        # Recent transactions
        # -------------------------------------------------

        transactions = []

        if account:

            cursor.execute(
                """
                SELECT *
                FROM transaction_history
                WHERE account_number=%s
                ORDER BY
                    transaction_date DESC,
                    transaction_time DESC,
                    transaction_id DESC
                LIMIT 5
                """,
                (
                    account["account_number"],
                )
            )

            transactions = cursor.fetchall()

        # -------------------------------------------------
        # Recent loans
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT
                loan_id,
                loan_type,
                loan_amount,
                loan_status,
                application_date
            FROM loan_application
            WHERE customer_id=%s
            ORDER BY loan_id DESC
            LIMIT 5
            """,
            (customer_id,)
        )

        loans = cursor.fetchall()

        return success_response(
            {
                "customer": customer,
                "account": account,
                "recent_transactions":
                    transactions,
                "recent_loans":
                    loans
            },

            "Dashboard loaded successfully."
        )

    except Exception as e:

        print(
            "Customer API Dashboard Error:",
            repr(e)
        )

        return error_response(
            "Unable to load dashboard.",
            500
        )

    finally:

        if cursor:
            cursor.close()

        if conn:
            conn.close()


# =========================================================
# TRANSACTION HISTORY
# =========================================================

@customer_api.route("/transactions", methods=["GET"])
def api_transactions():

    customer_id, error = get_customer_id_from_token()

    if error:

        return error_response(
            error,
            401
        )

    conn = None
    cursor = None

    try:

        conn = get_db_connection()

        cursor = conn.cursor(
            dictionary=True
        )

        # -------------------------------------------------
        # Get account
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT account_number
            FROM account
            WHERE customer_id=%s
            """,
            (customer_id,)
        )

        account = cursor.fetchone()

        if not account:

            return success_response(
                [],
                "No account found."
            )

        # -------------------------------------------------
        # Transactions
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT *
            FROM transaction_history
            WHERE account_number=%s
            ORDER BY
                transaction_date DESC,
                transaction_time DESC,
                transaction_id DESC
            """,
            (
                account["account_number"],
            )
        )

        transactions = cursor.fetchall()

        return success_response(
            transactions,
            "Transactions loaded successfully."
        )

    except Exception as e:

        print(
            "Customer API Transaction Error:",
            repr(e)
        )

        return error_response(
            "Unable to load transactions.",
            500
        )

    finally:

        if cursor:
            cursor.close()

        if conn:
            conn.close()


# =========================================================
# LOAN LIST
# =========================================================

@customer_api.route("/loans", methods=["GET"])
def api_loans():

    customer_id, error = get_customer_id_from_token()

    if error:

        return error_response(
            error,
            401
        )

    conn = None
    cursor = None

    try:

        conn = get_db_connection()

        cursor = conn.cursor(
            dictionary=True
        )

        cursor.execute(
            """
            SELECT *
            FROM loan_application
            WHERE customer_id=%s
            ORDER BY loan_id DESC
            """,
            (customer_id,)
        )

        loans = cursor.fetchall()

        return success_response(
            loans,
            "Loan applications loaded successfully."
        )

    except Exception as e:

        print(
            "Customer API Loan Error:",
            repr(e)
        )

        return error_response(
            "Unable to load loan applications.",
            500
        )

    finally:

        if cursor:
            cursor.close()

        if conn:
            conn.close()


# =========================================================
# SINGLE LOAN STATUS
# =========================================================

@customer_api.route(
    "/loan-status/<int:loan_id>",
    methods=["GET"]
)
def api_loan_status(loan_id):

    customer_id, error = get_customer_id_from_token()

    if error:

        return error_response(
            error,
            401
        )

    conn = None
    cursor = None

    try:

        conn = get_db_connection()

        cursor = conn.cursor(
            dictionary=True
        )

        # -------------------------------------------------
        # Customer can only view own loan
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT *
            FROM loan_application
            WHERE loan_id=%s
              AND customer_id=%s
            """,
            (
                loan_id,
                customer_id
            )
        )

        loan = cursor.fetchone()

        if not loan:

            return error_response(
                "Loan application not found.",
                404
            )

        # -------------------------------------------------
        # Latest ML prediction
        # -------------------------------------------------

        prediction = None

        try:

            cursor.execute(
                """
                SELECT *
                FROM loan_prediction
                WHERE loan_id=%s
                ORDER BY prediction_id DESC
                LIMIT 1
                """,
                (loan_id,)
            )

            prediction = cursor.fetchone()

        except Exception as prediction_error:

            print(
                "Prediction lookup warning:",
                repr(prediction_error)
            )

        return success_response(
            {
                "loan": loan,
                "prediction": prediction
            },

            "Loan status loaded successfully."
        )

    except Exception as e:

        print(
            "Customer API Loan Status Error:",
            repr(e)
        )

        return error_response(
            "Unable to load loan status.",
            500
        )

    finally:

        if cursor:
            cursor.close()

        if conn:
            conn.close()


# =========================================================
# UPDATE PROFILE
# =========================================================

@customer_api.route("/profile", methods=["PUT"])
def api_update_profile():

    customer_id, error = get_customer_id_from_token()

    if error:

        return error_response(
            error,
            401
        )

    data = request.get_json(silent=True)

    if not data:

        return error_response(
            "JSON request body is required."
        )

    fullname = str(
        data.get("fullname", "")
    ).strip()

    email = str(
        data.get("email", "")
    ).strip()

    mobile = str(
        data.get("mobile", "")
    ).strip()

    address = str(
        data.get("address", "")
    ).strip()

    if not fullname:

        return error_response(
            "Full name is required."
        )

    if not email:

        return error_response(
            "Email is required."
        )

    if not mobile:

        return error_response(
            "Mobile number is required."
        )

    if not address:

        return error_response(
            "Address is required."
        )

    conn = None
    cursor = None

    try:

        conn = get_db_connection()

        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE customer
            SET
                full_name=%s,
                email=%s,
                mobile=%s,
                address=%s
            WHERE customer_id=%s
            """,
            (
                fullname,
                email,
                mobile,
                address,
                customer_id
            )
        )

        conn.commit()

        return success_response(
            message="Profile updated successfully."
        )

    except Exception as e:

        if conn:
            conn.rollback()

        print(
            "Customer API Update Profile Error:",
            repr(e)
        )

        return error_response(
            "Unable to update profile.",
            500
        )

    finally:

        if cursor:
            cursor.close()

        if conn:
            conn.close()


# =========================================================
# CHANGE PASSWORD
# =========================================================

@customer_api.route(
    "/change-password",
    methods=["PUT"]
)
def api_change_password():

    customer_id, error = get_customer_id_from_token()

    if error:

        return error_response(
            error,
            401
        )

    data = request.get_json(silent=True)

    if not data:

        return error_response(
            "JSON request body is required."
        )

    current_password = str(
        data.get("current_password", "")
    )

    new_password = str(
        data.get("new_password", "")
    )

    confirm_password = str(
        data.get("confirm_password", "")
    )

    if not current_password:

        return error_response(
            "Current password is required."
        )

    if not new_password:

        return error_response(
            "New password is required."
        )

    if new_password != confirm_password:

        return error_response(
            "New password and confirm password do not match."
        )

    # -------------------------------------------------
    # Password validation
    # -------------------------------------------------

    pattern = (
        r"^(?=.*[a-z])"
        r"(?=.*[A-Z])"
        r"(?=.*\d)"
        r"(?=.*[@$!%*?&])"
        r".{8,}$"
    )

    if not re.match(
        pattern,
        new_password
    ):

        return error_response(
            "Password must contain at least 8 characters, "
            "uppercase, lowercase, number and special character."
        )

    conn = None
    cursor = None

    try:

        conn = get_db_connection()

        cursor = conn.cursor(
            dictionary=True
        )

        cursor.execute(
            """
            SELECT password
            FROM customer
            WHERE customer_id=%s
            """,
            (customer_id,)
        )

        customer = cursor.fetchone()

        if not customer:

            return error_response(
                "Customer not found.",
                404
            )

        stored_password = customer["password"]

        password_correct = False

        try:

            password_correct = check_password_hash(
                stored_password,
                current_password
            )

        except Exception:

            password_correct = False

        # Old plain-text support

        if (
            not password_correct
            and stored_password == current_password
        ):

            password_correct = True

        if not password_correct:

            return error_response(
                "Current password is incorrect.",
                401
            )

        # -------------------------------------------------
        # Hash new password
        # -------------------------------------------------

        password_hash = generate_password_hash(
            new_password
        )

        cursor.execute(
            """
            UPDATE customer
            SET password=%s
            WHERE customer_id=%s
            """,
            (
                password_hash,
                customer_id
            )
        )

        conn.commit()

        return success_response(
            message="Password changed successfully."
        )

    except Exception as e:

        if conn:
            conn.rollback()

        print(
            "Customer API Password Error:",
            repr(e)
        )

        return error_response(
            "Unable to change password.",
            500
        )

    finally:

        if cursor:
            cursor.close()

        if conn:
            conn.close()


# =========================================================
# LOGOUT
# =========================================================

@customer_api.route(
    "/logout",
    methods=["POST"]
)
def api_logout():

    # Token is stateless, so there is no server session
    # to clear here.

    return success_response(
        message="Logout successful. Remove the token from the mobile app."
    )