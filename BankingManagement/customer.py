from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import random
import os
import uuid
from werkzeug.utils import secure_filename
from flask import current_app
from datetime import datetime, timedelta
from db import get_db_connection
import re

customer = Blueprint("customer", __name__)

# -----------------------------
# Customer Login
# -----------------------------
@customer.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "GET":
        return render_template("index.html")

    username = request.form["username"].strip()
    password = request.form["password"]

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:

        # Get customer using username
        cursor.execute("""
            SELECT *
            FROM customer
            WHERE username = %s
        """, (username,))

        customer_data = cursor.fetchone()

        if customer_data is None:
            flash("Invalid Username or Password", "error")
            return redirect(url_for("customer.login"))

        stored_password = customer_data["password"]

        # -----------------------------------------
        # Check password
        # -----------------------------------------

        password_valid = False

        # For newly registered / reset passwords
        # stored password will be hashed
        try:
            password_valid = check_password_hash(
                stored_password,
                password
            )
        except Exception:
            password_valid = False

        # -----------------------------------------
        # Support old users whose password is
        # still stored as plain text
        # -----------------------------------------

        if not password_valid and stored_password == password:

            password_valid = True

            # Convert old plain-text password
            # into hashed password
            new_password_hash = generate_password_hash(password)

            cursor.execute("""
                UPDATE customer
                SET password = %s
                WHERE customer_id = %s
            """, (
                new_password_hash,
                customer_data["customer_id"]
            ))

            conn.commit()

        # -----------------------------------------
        # Login success
        # -----------------------------------------

        if password_valid:

            session["customer_id"] = customer_data["customer_id"]

            return redirect(url_for("customer.dashboard"))

        # -----------------------------------------
        # Login failed
        # -----------------------------------------

        flash("Invalid Username or Password", "error")
        return redirect(url_for("customer.login"))

    except Exception as e:

        print("Login Error:", e)

        flash("Login failed. Please try again.", "error")
        return redirect(url_for("customer.login"))

    finally:

        cursor.close()
        conn.close()
        
# -----------------------------
# Register
# -----------------------------
@customer.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        fullname = request.form["fullname"]
        email = request.form["email"]
        mobile = request.form["mobile"]
        address = request.form["address"]
        aadhaar = request.form["aadhaar"]
        accounttype = request.form["accounttype"]
        dob = request.form["dob"]
        gender = request.form["gender"]
        username = request.form["username"]
        password = request.form["password"]
        confirm = request.form["confirmpassword"]

        # --------------------------------
        # Password confirmation
        # --------------------------------
        if password != confirm:

            flash("Password and Confirm Password do not match.", "error")

            return redirect(url_for("customer.register"))

        # --------------------------------
        # Password validation
        # --------------------------------
        pattern = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&]).{8,}$'

        if not re.match(pattern, password):

            flash(
                "Password must contain Uppercase, Lowercase, "
                "Number and Special Character.",
                "error"
            )

            return redirect(url_for("customer.register"))

        conn = get_db_connection()
        cursor = conn.cursor()

        try:

            # --------------------------------
            # Check username
            # --------------------------------
            cursor.execute(
                """
                SELECT customer_id
                FROM customer
                WHERE username=%s
                """,
                (username,)
            )

            if cursor.fetchone():

                flash("Username already exists.", "error")

                return redirect(url_for("customer.register"))

            # --------------------------------
            # HASH PASSWORD
            # --------------------------------
            password_hash = generate_password_hash(password)

            # --------------------------------
            # Insert customer
            # --------------------------------
            sql = """
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
            (%s,%s,%s,%s,%s,%s,%s,%s,%s,CURDATE(),%s)
            """

            values = (
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

            cursor.execute(sql, values)

            # --------------------------------
            # Get newly created customer ID
            # --------------------------------
            customer_id = cursor.lastrowid

            # --------------------------------
            # Generate unique 12-digit account
            # number
            # --------------------------------
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

            # --------------------------------
            # SecureBank IFSC
            # --------------------------------
            ifsc_code = "SECU0000001"

            branch_name = "Main Branch"

            # --------------------------------
            # Create account
            # --------------------------------
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
                (%s,%s,%s,%s,%s,%s,%s,CURDATE())
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

            # --------------------------------
            # Commit
            # --------------------------------
            conn.commit()

            flash(
                f"Registration Successful! "
                f"Your SecureBank Account Number is {account_number}",
                "success"
            )

            return redirect(url_for("customer.login"))

        except Exception as e:

            conn.rollback()

            print("Registration Error:", e)

            flash(
                "Registration failed. Please try again.",
                "error"
            )

            return redirect(url_for("customer.register"))

        finally:

            cursor.close()
            conn.close()

    return render_template("register.html")

# -----------------------------
# Dashboard
# -----------------------------
@customer.route("/dashboard")
def dashboard():

    if "customer_id" not in session:
        return redirect(url_for("customer.login"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Customer Details
    cursor.execute(
        "SELECT * FROM customer WHERE customer_id=%s",
        (session["customer_id"],)
    )
    customer_data = cursor.fetchone()

    # Account Details
    cursor.execute(
        "SELECT * FROM account WHERE customer_id=%s",
        (session["customer_id"],)
    )
    account_data = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template(
        "dashboard.html",
        customer=customer_data,
        account=account_data
    )
# -----------------------------
# Profile
# -----------------------------
@customer.route("/profile", methods=["GET", "POST"])
def profile():

    if "customer_id" not in session:
        return redirect(url_for("customer.login"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # -------------------------------
    # PROFILE PHOTO UPLOAD
    # -------------------------------
    if request.method == "POST":

        photo = request.files.get("profile_photo")

        if not photo or photo.filename == "":
            flash("Please select a photo.")
            cursor.close()
            conn.close()
            return redirect(url_for("customer.profile"))

        allowed_extensions = {"jpg", "jpeg", "png", "webp"}

        filename = secure_filename(photo.filename)

        if "." not in filename:
            flash("Invalid image file.")
            cursor.close()
            conn.close()
            return redirect(url_for("customer.profile"))

        extension = filename.rsplit(".", 1)[1].lower()

        if extension not in allowed_extensions:
            flash("Only JPG, JPEG, PNG and WEBP images are allowed.")
            cursor.close()
            conn.close()
            return redirect(url_for("customer.profile"))

        # Create upload folder
        upload_folder = os.path.join(
            current_app.root_path,
            "static",
            "uploads",
            "profile_photos"
        )

        os.makedirs(upload_folder, exist_ok=True)

        # Unique filename
        new_filename = (
            f"customer_{session['customer_id']}_"
            f"{uuid.uuid4().hex}.{extension}"
        )

        file_path = os.path.join(
            upload_folder,
            new_filename
        )

        # Save photo
        photo.save(file_path)

        # Database path
        photo_db_path = f"uploads/profile_photos/{new_filename}"

        # Get old photo
        cursor.execute(
            "SELECT profile_photo FROM customer WHERE customer_id=%s",
            (session["customer_id"],)
        )

        old_data = cursor.fetchone()

        old_photo = None

        if old_data:
            old_photo = old_data.get("profile_photo")

        # Update new photo
        cursor.execute(
            """
            UPDATE customer
            SET profile_photo=%s
            WHERE customer_id=%s
            """,
            (
                photo_db_path,
                session["customer_id"]
            )
        )

        conn.commit()

        # Delete old uploaded photo
        if old_photo and old_photo != "images/profile.jpeg":

            old_file_path = os.path.join(
                current_app.root_path,
                "static",
                old_photo
            )

            if os.path.exists(old_file_path):
                try:
                    os.remove(old_file_path)
                except:
                    pass

        flash("Profile Photo Updated Successfully")

        cursor.close()
        conn.close()

        return redirect(url_for("customer.profile"))

    # -------------------------------
    # CUSTOMER DETAILS
    # -------------------------------
    cursor.execute(
        "SELECT * FROM customer WHERE customer_id=%s",
        (session["customer_id"],)
    )

    customer_data = cursor.fetchone()

    # -------------------------------
    # ACCOUNT DETAILS
    # -------------------------------
    cursor.execute(
        "SELECT * FROM account WHERE customer_id=%s",
        (session["customer_id"],)
    )

    account_data = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template(
        "profile.html",
        customer=customer_data,
        account=account_data
    )
# -----------------------------
# Account Details
# -----------------------------
@customer.route("/accountdetails")
def accountdetails():

    if "customer_id" not in session:
        return redirect(url_for("customer.login"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Customer Details
    cursor.execute(
        "SELECT * FROM customer WHERE customer_id=%s",
        (session["customer_id"],)
    )
    customer_data = cursor.fetchone()

    # Account Details
    cursor.execute(
        "SELECT * FROM account WHERE customer_id=%s",
        (session["customer_id"],)
    )
    account_data = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template(
        "accountdetails.html",
        customer=customer_data,
        account=account_data
    )
# -----------------------------
# Transaction History
# -----------------------------
@customer.route("/transactionhistory")
def transactionhistory():

    if "customer_id" not in session:
        return redirect(url_for("customer.login"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Get account number
    cursor.execute("""
        SELECT account_number
        FROM account
        WHERE customer_id=%s
    """, (session["customer_id"],))

    account = cursor.fetchone()

    transactions = []

    if account:

        cursor.execute("""
            SELECT *
            FROM transaction_history
            WHERE account_number=%s
            ORDER BY transaction_id DESC
        """, (account["account_number"],))

        transactions = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "transactionhistory.html",
        transactions=transactions
    )
# -----------------------------
# Download Statement
# -----------------------------
@customer.route("/download_statement")
def download_statement():

    if "customer_id" not in session:
        return redirect(url_for("customer.login"))

    flash("Statement Download Feature Coming Soon")

    return redirect(url_for("customer.transactionhistory"))

# -----------------------------
# Deposit Money
# -----------------------------
@customer.route("/deposit", methods=["GET", "POST"])
def deposit():

    if "customer_id" not in session:
        return redirect(url_for("customer.login"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Customer Details
    cursor.execute(
        "SELECT * FROM customer WHERE customer_id=%s",
        (session["customer_id"],)
    )

    customer_data = cursor.fetchone()

    # Account Details
    cursor.execute(
        "SELECT * FROM account WHERE customer_id=%s",
        (session["customer_id"],)
    )

    account_data = cursor.fetchone()

    if request.method == "POST":

        amount = float(request.form["amount"])

        if amount <= 0:
            flash("Enter a valid amount")
            cursor.close()
            conn.close()
            return redirect(url_for("customer.deposit"))

        # Update Account Balance
        cursor.execute(
            """
            UPDATE account
            SET balance = balance + %s
            WHERE customer_id = %s
            """,
            (amount, session["customer_id"])
        )

        # Insert Transaction History
        cursor.execute(
            """
            INSERT INTO transaction_history
            (
                account_number,
                transaction_type,
                amount,
                transaction_date,
                transaction_time,
                description,
                status
            )
            VALUES
            (
                %s,
                'Deposit',
                %s,
                CURDATE(),
                CURTIME(),
                %s,
                'Success'
            )
            """,
            (
                account_data["account_number"],
                amount,
                "Amount Deposited"
            )
        )

        conn.commit()

        flash("Amount Deposited Successfully")

        cursor.close()
        conn.close()

        return redirect(url_for("customer.deposit"))

    cursor.close()
    conn.close()

    return render_template(
        "deposit.html",
        customer=customer_data,
        account=account_data
    )

# -----------------------------
# Withdraw Money
# -----------------------------
@customer.route("/withdraw", methods=["GET", "POST"])
def withdraw():

    if "customer_id" not in session:
        return redirect(url_for("customer.login"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Customer Details
    cursor.execute(
        "SELECT * FROM customer WHERE customer_id=%s",
        (session["customer_id"],)
    )

    customer_data = cursor.fetchone()

    # Account Details
    cursor.execute(
        "SELECT * FROM account WHERE customer_id=%s",
        (session["customer_id"],)
    )

    account_data = cursor.fetchone()

    if request.method == "POST":

        amount = float(request.form["amount"])

        if amount <= 0:
            flash("Enter a valid amount")
            cursor.close()
            conn.close()
            return redirect(url_for("customer.withdraw"))

        # Check Balance
        if account_data["balance"] < amount:
            flash("Insufficient Balance")
            cursor.close()
            conn.close()
            return redirect(url_for("customer.withdraw"))

        # Update Account Balance
        cursor.execute(
            """
            UPDATE account
            SET balance = balance - %s
            WHERE customer_id = %s
            """,
            (amount, session["customer_id"])
        )

        # Insert Transaction History
        cursor.execute(
            """
            INSERT INTO transaction_history
            (
                account_number,
                transaction_type,
                amount,
                transaction_date,
                transaction_time,
                description,
                status
            )
            VALUES
            (
                %s,
                'Withdraw',
                %s,
                CURDATE(),
                CURTIME(),
                %s,
                'Success'
            )
            """,
            (
                account_data["account_number"],
                amount,
                "Amount Withdrawn"
            )
        )

        conn.commit()

        flash("Amount Withdrawn Successfully")

        cursor.close()
        conn.close()

        return redirect(url_for("customer.withdraw"))

    cursor.close()
    conn.close()

    return render_template(
        "withdraw.html",
        customer=customer_data,
        account=account_data
    )
# -----------------------------
# Fund Transfer
# -----------------------------
@customer.route("/fundtransfer", methods=["GET", "POST"])
def fundtransfer():

    if "customer_id" not in session:
        return redirect(url_for("customer.login"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Logged-in Customer Details
    cursor.execute(
        "SELECT * FROM customer WHERE customer_id=%s",
        (session["customer_id"],)
    )
    customer_data = cursor.fetchone()

    # Sender Account Details
    cursor.execute(
        "SELECT * FROM account WHERE customer_id=%s",
        (session["customer_id"],)
    )
    account_data = cursor.fetchone()

    # =========================
    # FUND TRANSFER - POST
    # =========================
    if request.method == "POST":

        receiver_account = request.form["receiver_account"]
        amount = float(request.form["amount"])

        # Amount validation
        if amount <= 0:
            flash("Enter a valid amount")
            cursor.close()
            conn.close()
            return redirect(url_for("customer.fundtransfer"))

        # Check receiver account
        cursor.execute(
            """
            SELECT *
            FROM account
            WHERE account_number=%s
            """,
            (receiver_account,)
        )
        receiver_data = cursor.fetchone()

        if not receiver_data:
            flash("Receiver Account Not Found")
            cursor.close()
            conn.close()
            return redirect(url_for("customer.fundtransfer"))

        # Cannot transfer to own account
        if int(receiver_account) == int(account_data["account_number"]):
            flash("You cannot transfer money to your own account")
            cursor.close()
            conn.close()
            return redirect(url_for("customer.fundtransfer"))

        # Check sufficient balance
        if account_data["balance"] < amount:
            flash("Insufficient Balance")
            cursor.close()
            conn.close()
            return redirect(url_for("customer.fundtransfer"))

        # Check receiver account active
        if receiver_data["account_status"] != "Active":
            flash("Receiver Account is not Active")
            cursor.close()
            conn.close()
            return redirect(url_for("customer.fundtransfer"))

        # =========================
        # Deduct from Sender
        # =========================
        cursor.execute(
            """
            UPDATE account
            SET balance = balance - %s
            WHERE account_number=%s
            """,
            (amount, account_data["account_number"])
        )

        # =========================
        # Add to Receiver
        # =========================
        cursor.execute(
            """
            UPDATE account
            SET balance = balance + %s
            WHERE account_number=%s
            """,
            (amount, receiver_account)
        )

        # =========================
        # Sender Transaction
        # =========================
        cursor.execute(
            """
            INSERT INTO transaction_history
            (
                account_number,
                receiver_account,
                sender_account,
                transaction_type,
                amount,
                transaction_date,
                transaction_time,
                description,
                status
            )
            VALUES
            (
                %s,
                %s,
                %s,
                'Transfer',
                %s,
                CURDATE(),
                CURTIME(),
                'Fund Transfer',
                'Success'
            )
            """,
            (
                account_data["account_number"],
                receiver_account,
                account_data["account_number"],
                amount
            )
        )

        # =========================
        # Receiver Transaction
        # =========================
        cursor.execute(
            """
            INSERT INTO transaction_history
            (
                account_number,
                receiver_account,
                sender_account,
                transaction_type,
                amount,
                transaction_date,
                transaction_time,
                description,
                status
            )
            VALUES
            (
                %s,
                %s,
                %s,
                'Transfer',
                %s,
                CURDATE(),
                CURTIME(),
                'Fund Transfer Received',
                'Success'
            )
            """,
            (
                receiver_account,
                receiver_account,
                account_data["account_number"],
                amount
            )
        )

        conn.commit()

        flash("Fund Transfer Successful")

        cursor.close()
        conn.close()

        return redirect(url_for("customer.fundtransfer"))

    # =========================
    # Recent Transactions
    # =========================
    cursor.execute(
        """
        SELECT
            transaction_date,
            transaction_time,
            amount,
            description,
            status
        FROM transaction_history
        WHERE account_number=%s
        ORDER BY transaction_date DESC,
                 transaction_time DESC,
                 transaction_id DESC
        LIMIT 5
        """,
        (account_data["account_number"],)
    )

    transaction_data = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "fundtransfer.html",
        customer=customer_data,
        account=account_data,
        transactions=transaction_data
    )
# -----------------------------
# Update Profile
# -----------------------------
@customer.route("/update", methods=["GET", "POST"])
def update():

    if "customer_id" not in session:
        return redirect(url_for("customer.login"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":

        fullname = request.form["fullname"]
        email = request.form["email"]
        mobile = request.form["mobile"]
        address = request.form["address"]

        cursor.execute("""
            UPDATE customer
            SET full_name=%s,
                email=%s,
                mobile=%s,
                address=%s
            WHERE customer_id=%s
        """, (
            fullname,
            email,
            mobile,
            address,
            session["customer_id"]
        ))

        conn.commit()

        flash("Profile Updated Successfully")

        cursor.close()
        conn.close()

        return redirect(url_for("customer.profile"))

    cursor.execute(
        "SELECT * FROM customer WHERE customer_id=%s",
        (session["customer_id"],)
    )

    customer_data = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template(
        "update.html",
        customer=customer_data
    )
# -----------------------------
# Change Password
# -----------------------------
@customer.route("/changepassword", methods=["GET", "POST"])
def changepassword():

    if "customer_id" not in session:
        return redirect(url_for("customer.login"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":

        current_password = request.form["current_password"]
        new_password = request.form["new_password"]
        confirm_password = request.form["confirm_password"]

        cursor.execute(
            "SELECT password FROM customer WHERE customer_id=%s",
            (session["customer_id"],)
        )

        customer_data = cursor.fetchone()

        stored_password = customer_data["password"]

        # Check Current Password against hashed password
        try:
            password_correct = check_password_hash(
                stored_password,
                current_password
            )
        except Exception:
            password_correct = False

        # Support old plain-text passwords also
        if not password_correct and stored_password == current_password:
            password_correct = True

        if not password_correct:

            flash("Current Password is Incorrect", "error")

            cursor.close()
            conn.close()

            return redirect(url_for("customer.changepassword"))

        # New password validation
        if len(new_password) < 8:
            flash("New Password must contain at least 8 characters.", "error")

            cursor.close()
            conn.close()

            return redirect(url_for("customer.changepassword"))

        if not any(char.isupper() for char in new_password):
            flash("New Password must contain an uppercase letter.", "error")

            cursor.close()
            conn.close()

            return redirect(url_for("customer.changepassword"))

        if not any(char.islower() for char in new_password):
            flash("New Password must contain a lowercase letter.", "error")

            cursor.close()
            conn.close()

            return redirect(url_for("customer.changepassword"))

        if not any(char.isdigit() for char in new_password):
            flash("New Password must contain a number.", "error")

            cursor.close()
            conn.close()

            return redirect(url_for("customer.changepassword"))

        if not any(not char.isalnum() for char in new_password):
            flash("New Password must contain a special character.", "error")

            cursor.close()
            conn.close()

            return redirect(url_for("customer.changepassword"))

        # Confirm password
        if new_password != confirm_password:

            flash("New Password and Confirm Password do not match.", "error")

            cursor.close()
            conn.close()

            return redirect(url_for("customer.changepassword"))

        # Hash the new password
        password_hash = generate_password_hash(new_password)

        cursor.execute("""
            UPDATE customer
            SET password=%s
            WHERE customer_id=%s
        """, (
            password_hash,
            session["customer_id"]
        ))

        conn.commit()

        flash("Password Changed Successfully", "success")

        cursor.close()
        conn.close()

        return redirect(url_for("customer.profile"))

    cursor.close()
    conn.close()

    return render_template("changepassword.html")

# -----------------------------
# Logout
# -----------------------------
@customer.route("/logout")
def logout():

    session.clear()

    flash("Logged Out Successfully")

    return redirect(url_for("customer.login"))


# -----------------------------
# Customer Details
# -----------------------------
@customer.route("/customerdetails")
def customerdetails():

    if "customer_id" not in session:
        return redirect(url_for("customer.login"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM customer WHERE customer_id=%s",
        (session["customer_id"],)
    )

    customer_data = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template(
        "customerdetails.html",
        customer=customer_data
    )

# -----------------------------
# Balance Enquiry
# -----------------------------
@customer.route("/balance")
def balance():

    if "customer_id" not in session:
        return redirect(url_for("customer.login"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Get Account Details
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
        (session["customer_id"],)
    )

    balance_data = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template(
        "balance.html",
        balance=balance_data
    )

# -----------------------------
# Mini Statement
# -----------------------------
@customer.route("/ministatement")
def ministatement():
    if "customer_id" not in session:
        return redirect(url_for("customer.login"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Get customer's account number
    cursor.execute(
        """
        SELECT account_number
        FROM account
        WHERE customer_id=%s
        """,
        (session["customer_id"],)
    )

    account_data = cursor.fetchone()

    if not account_data:
        cursor.close()
        conn.close()
        flash("Account not found")
        return redirect(url_for("customer.dashboard"))

    # Get latest 5 transactions
    cursor.execute(
        """
        SELECT *
        FROM transaction_history
        WHERE account_number=%s
        ORDER BY transaction_date DESC,
                 transaction_time DESC,
                 transaction_id DESC
        LIMIT 5
        """,
        (account_data["account_number"],)
    )

    transactions = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "ministatement.html",
        transactions=transactions
    )
# -----------------------------
# Notifications
# -----------------------------
@customer.route("/notifications")
def notifications():

    if "customer_id" not in session:
        return redirect(url_for("customer.login"))

    return render_template("notifications.html")

# -----------------------------
# ForgetPassword
# -----------------------------
@customer.route("/forgotpassword", methods=["GET", "POST"])
def forgotpassword():

    if request.method == "POST":

        customer_id = request.form["customer_id"]
        email = request.form["email"].strip()
        mobile = request.form["mobile"].strip()

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT customer_id, email, mobile
            FROM customer
            WHERE customer_id = %s
              AND email = %s
              AND mobile = %s
        """, (customer_id, email, mobile))

        customer_data = cursor.fetchone()

        cursor.close()
        conn.close()

        if customer_data is None:
            flash("Customer ID, Email or Mobile Number is incorrect.", "error")
            return redirect(url_for("customer.forgotpassword"))

        # Generate 6 digit OTP
        otp = str(random.randint(100000, 999999))

        # Store OTP temporarily in session
        session["reset_customer_id"] = customer_data["customer_id"]
        session["reset_otp"] = otp
        session["otp_expiry"] = (
            datetime.now() + timedelta(minutes=5)
        ).timestamp()

        # Temporary: display OTP in terminal
        print("PASSWORD RESET OTP:", otp)

        return redirect(url_for("customer.verifyotp"))

    return render_template("forgotpassword.html")

# -----------------------------
# OTP Verification
# -----------------------------
@customer.route("/verifyotp", methods=["GET", "POST"])
def verifyotp():

    if "reset_customer_id" not in session:
        return redirect(url_for("customer.forgotpassword"))

    if request.method == "POST":

        entered_otp = request.form["otp"].strip()

        stored_otp = session.get("reset_otp")
        expiry_time = session.get("otp_expiry")

        # Check OTP expiry
        if not expiry_time or datetime.now().timestamp() > expiry_time:

            session.pop("reset_otp", None)
            session.pop("otp_expiry", None)

            flash("OTP has expired. Please request a new OTP.", "error")

            return redirect(url_for("customer.forgotpassword"))

        # Check OTP
        if entered_otp != stored_otp:

            flash("Invalid OTP. Please try again.", "error")

            return redirect(url_for("customer.verifyotp"))

        # OTP verified
        session["otp_verified"] = True

        session.pop("reset_otp", None)
        session.pop("otp_expiry", None)

        return redirect(url_for("customer.resetpassword"))

    return render_template("verifyotp.html")
# -----------------------------
# Reset Password
# -----------------------------
# -----------------------------
# Reset Password
# -----------------------------
@customer.route("/resetpassword", methods=["GET", "POST"])
def resetpassword():

    # Check customer reset session
    if "reset_customer_id" not in session:

        return redirect(
            url_for("customer.forgotpassword")
        )

    # Check OTP verification
    if not session.get("otp_verified"):

        return redirect(
            url_for("customer.verifyotp")
        )

    if request.method == "POST":

        new_password = request.form["new_password"]
        confirm_password = request.form["confirm_password"]

        # --------------------------------
        # Confirm password
        # --------------------------------
        if new_password != confirm_password:

            flash(
                "Passwords do not match.",
                "error"
            )

            return redirect(
                url_for("customer.resetpassword")
            )

        # --------------------------------
        # Password validation
        # --------------------------------
        pattern = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&]).{8,}$'

        if not re.match(pattern, new_password):

            flash(
                "Password must contain at least 8 characters, "
                "uppercase, lowercase, number and special character.",
                "error"
            )

            return redirect(
                url_for("customer.resetpassword")
            )

        # --------------------------------
        # HASH NEW PASSWORD
        # --------------------------------
        password_hash = generate_password_hash(
            new_password
        )

        conn = get_db_connection()
        cursor = conn.cursor()

        try:

            # --------------------------------
            # Update password
            # --------------------------------
            cursor.execute("""
                UPDATE customer
                SET password = %s
                WHERE customer_id = %s
            """, (
                password_hash,
                session["reset_customer_id"]
            ))

            conn.commit()

            # --------------------------------
            # Clear reset session
            # --------------------------------
            session.pop("reset_customer_id", None)
            session.pop("otp_verified", None)

            # --------------------------------
            # Password success page
            # --------------------------------
            return redirect(
                url_for("customer.passwordsuccess")
            )

        except Exception as e:

            conn.rollback()

            print("Reset Password Error:", e)

            flash(
                "Password reset failed. Please try again.",
                "error"
            )

            return redirect(
                url_for("customer.resetpassword")
            )

        finally:

            cursor.close()
            conn.close()

    return render_template("resetpassword.html")
# -----------------------------
# Reset Password Succesfull
# -----------------------------
@customer.route("/passwordsuccess")
def passwordsuccess():

    return render_template("passwordsuccess.html")
# -----------------------------
# Help
# -----------------------------
@customer.route("/help")
def help():

    return render_template("help.html")
