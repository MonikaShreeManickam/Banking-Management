from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from db import get_db_connection
import os
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from flask import send_file
from io import BytesIO
from datetime import datetime, timedelta
import uuid
from functools import wraps
from werkzeug.utils import secure_filename
# Password hashing will be used later
from werkzeug.security import generate_password_hash, check_password_hash

admin = Blueprint("admin", __name__)

def role_required(*allowed_roles):
    def decorator(view_function):
        @wraps(view_function)
        def wrapper(*args, **kwargs):

            # Not logged in
            if "admin_id" not in session:
                return redirect(url_for("admin.adminlogin"))

            # Get logged-in user's role
            user_role = session.get("admin_role")

            # Check permission
            if user_role not in allowed_roles:
                flash("You do not have permission to access this page.")
                return redirect(url_for("admin.admindashboard"))

            return view_function(*args, **kwargs)

        return wrapper

    return decorator

@admin.route("/adminlogin", methods=["GET", "POST"])
def adminlogin():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT *
            FROM admin
            WHERE username=%s
            AND status='Active'
            """,
            (username,)
        )

        admin_data = cursor.fetchone()

        cursor.close()
        conn.close()

        if admin_data and check_password_hash(
            admin_data["password"],
            password
        ):

            session["admin_id"] = admin_data["admin_id"]
            session["admin_name"] = admin_data["admin_name"]
            session["admin_role"] = admin_data["role"]
            session["admin_branch"] = admin_data["branch"]

            return redirect(url_for("admin.admindashboard"))

        flash("Invalid Username or Password")

        return redirect(url_for("admin.adminlogin"))

    return render_template("adminlogin.html")


@admin.route("/admindashboard")
@role_required("Administrator", "Manager", "Specialist Officer", "Clerk")
def admindashboard():

    # -------------------------------------------------
    # ADMIN LOGIN CHECK
    # -------------------------------------------------

    if "admin_id" not in session:
        flash("Please login as administrator.")
        return redirect(url_for("admin.adminlogin"))


    # -------------------------------------------------
    # DATABASE CONNECTION
    # -------------------------------------------------

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)


    try:

        # -------------------------------------------------
        # GET LOGGED-IN ADMIN DETAILS
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT *
            FROM admin
            WHERE admin_id = %s
            """,
            (session["admin_id"],)
        )

        admin_data = cursor.fetchone()


        if not admin_data:
            flash("Administrator details not found.")
            return redirect(url_for("admin.adminlogin"))


        # -------------------------------------------------
        # DASHBOARD COUNTS
        # -------------------------------------------------

        # Total Customers
        cursor.execute(
            "SELECT COUNT(*) AS total FROM customer"
        )

        total_customers = cursor.fetchone()["total"]


        # Total Active Accounts
        cursor.execute(
            """
            SELECT COUNT(*) AS total
            FROM account
            WHERE account_status = 'Active'
            """
        )

        total_accounts = cursor.fetchone()["total"]


        # Total Transactions
        cursor.execute(
            """
            SELECT COUNT(*) AS total
            FROM transaction_history
            """
        )

        total_transactions = cursor.fetchone()["total"]


        # Total Loan Applications
        cursor.execute(
            """
            SELECT COUNT(*) AS total
            FROM loan_application
            """
        )

        total_loans = cursor.fetchone()["total"]


        # -------------------------------------------------
        # CLOSE DATABASE
        # -------------------------------------------------

        cursor.close()
        conn.close()


        # -------------------------------------------------
        # SEND DATA TO ADMIN DASHBOARD
        # -------------------------------------------------

        return render_template(
            "admindashboard.html",

            admin=admin_data,

            total_customers=total_customers,
            total_accounts=total_accounts,
            total_transactions=total_transactions,
            total_loans=total_loans
        )


    except Exception as e:

        print(
            "Admin Dashboard Error:",
            repr(e)
        )

        cursor.close()
        conn.close()

        flash(
            f"Unable to load admin dashboard: {str(e)}"
        )

        return redirect(url_for("admin.adminlogin"))

@admin.route("/adminprofile", methods=["GET", "POST"])
@role_required("Administrator", "Manager", "Specialist Officer", "Clerk")
def adminprofile():

    if "admin_id" not in session:
        return redirect(url_for("admin.adminlogin"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # =====================================================
    # PROFILE PHOTO UPLOAD
    # =====================================================

    if request.method == "POST":

        photo = request.files.get("profile_photo")

        if not photo or photo.filename == "":
            flash("Please select a photo.")
            cursor.close()
            conn.close()
            return redirect(url_for("admin.adminprofile"))

        # Allowed image formats
        allowed_extensions = {
            "jpg",
            "jpeg",
            "png",
            "webp"
        }

        filename = secure_filename(photo.filename)

        if "." not in filename:
            flash("Invalid image file.")
            cursor.close()
            conn.close()
            return redirect(url_for("admin.adminprofile"))

        extension = filename.rsplit(".", 1)[1].lower()

        if extension not in allowed_extensions:
            flash("Only JPG, JPEG, PNG and WEBP images are allowed.")
            cursor.close()
            conn.close()
            return redirect(url_for("admin.adminprofile"))

        # =================================================
        # CREATE UPLOAD FOLDER
        # =================================================

        upload_folder = os.path.join(
            current_app.root_path,
            "static",
            "uploads",
            "admin_photos"
        )

        os.makedirs(upload_folder, exist_ok=True)

        # =================================================
        # UNIQUE FILE NAME
        # =================================================

        new_filename = (
            f"admin_{session['admin_id']}_"
            f"{uuid.uuid4().hex}.{extension}"
        )

        file_path = os.path.join(
            upload_folder,
            new_filename
        )

        # Save image
        photo.save(file_path)

        # Path stored in database
        photo_db_path = (
            f"uploads/admin_photos/{new_filename}"
        )

        # =================================================
        # GET OLD PHOTO
        # =================================================

        cursor.execute(
            """
            SELECT profile_photo
            FROM admin
            WHERE admin_id=%s
            """,
            (session["admin_id"],)
        )

        old_data = cursor.fetchone()

        old_photo = None

        if old_data:
            old_photo = old_data.get("profile_photo")

        # =================================================
        # UPDATE DATABASE
        # =================================================

        cursor.execute(
            """
            UPDATE admin
            SET profile_photo=%s
            WHERE admin_id=%s
            """,
            (
                photo_db_path,
                session["admin_id"]
            )
        )

        conn.commit()

        # =================================================
        # DELETE OLD PHOTO
        # =================================================

        if old_photo:

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

        return redirect(url_for("admin.adminprofile"))

    # =====================================================
    # GET ADMIN DETAILS
    # =====================================================

    cursor.execute(
        """
        SELECT *
        FROM admin
        WHERE admin_id=%s
        """,
        (session["admin_id"],)
    )

    admin_data = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template(
        "adminprofile.html",
        admin=admin_data
    )

@admin.route('/adminchangepassword', methods=['GET', 'POST'])
@role_required("Administrator", "Manager", "Specialist Officer", "Clerk")
def adminchangepassword():

    if 'admin_id' not in session:
        return redirect(url_for('admin.adminlogin'))

    if request.method == 'POST':
        old_password = request.form['old_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        if new_password == confirm_password:
            return render_template(
                'adminchangepassword.html',
                success="Password Changed Successfully!"
            )
        else:
            return render_template(
                'adminchangepassword.html',
                error="New Password and Confirm Password do not match!"
            )

    return render_template('adminchangepassword.html')

@admin.route('/viewcustomers')
@role_required("Administrator", "Manager", "Specialist Officer", "Clerk")
def viewcustomers():

    if 'admin_id' not in session:
        return redirect(url_for('admin.adminlogin'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM customer")
    customers = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        'viewcustomers.html',
        customers=customers
    )

@admin.route("/addcustomer", methods=["GET", "POST"])
@role_required("Administrator", "Manager", "Clerk")
def addcustomer():

    if "admin_id" not in session:
        return redirect(url_for("admin.adminlogin"))

    if request.method == "POST":

        fullname = request.form["fullname"]
        email = request.form["email"]
        mobile = request.form["mobile"]
        address = request.form["address"]
        dob = request.form["dob"]
        gender = request.form["gender"]
        account_type = request.form["account_type"]
        username = request.form["username"]
        password = request.form["password"]
        aadhaar = request.form["aadhaar"]

        conn = get_db_connection()
        cursor = conn.cursor()

        sql = """
        INSERT INTO customer
        (full_name,email,mobile,address,date_of_birth,
        gender,account_type,username,password,
        created_date,aadhaar)

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
            account_type,
            username,
            password,
            aadhaar
        )

        cursor.execute(sql, values)

        conn.commit()

        cursor.close()
        conn.close()

        flash("Customer Added Successfully")

        return redirect(url_for("admin.viewcustomers"))

    return render_template("addcustomer.html")

@admin.route("/updatecustomer/<int:id>", methods=["GET","POST"])
@role_required("Administrator", "Manager")
def updatecustomer(id):

    if "admin_id" not in session:
        return redirect(url_for("admin.adminlogin"))

    conn = get_db_connection()

    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":

        fullname = request.form["fullname"]
        email = request.form["email"]
        mobile = request.form["mobile"]
        address = request.form["address"]
        account_type = request.form["account_type"]

        sql = """
        UPDATE customer
        SET
        full_name=%s,
        email=%s,
        mobile=%s,
        address=%s,
        account_type=%s
        WHERE customer_id=%s
        """

        cursor.execute(
            sql,
            (
                fullname,
                email,
                mobile,
                address,
                account_type,
                id
            )
        )

        conn.commit()

        flash("Customer Updated Successfully")

        cursor.close()
        conn.close()

        return redirect(url_for("admin.viewcustomers"))

    cursor.execute(
        "SELECT * FROM customer WHERE customer_id=%s",
        (id,)
    )

    customer = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template(
        "updatecustomer.html",
        customer=customer
    )

@admin.route("/deletecustomer/<int:id>")
@role_required("Administrator")
def deletecustomer(id):

    if "admin_id" not in session:
        return redirect(url_for("admin.adminlogin"))

    conn = get_db_connection()

    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM customer WHERE customer_id=%s",
        (id,)
    )

    conn.commit()

    cursor.close()
    conn.close()

    flash("Customer Deleted Successfully")

    return redirect(url_for("admin.viewcustomers"))

@admin.route("/searchcustomer", methods=["POST"])
@role_required("Administrator", "Manager", "Specialist Officer", "Clerk")
def searchcustomer():

    keyword = request.form["keyword"]

    conn = get_db_connection()

    cursor = conn.cursor(dictionary=True)

    sql = """
    SELECT *
    FROM customer
    WHERE
    full_name LIKE %s
    OR username LIKE %s
    OR email LIKE %s
    """

    value = "%" + keyword + "%"

    cursor.execute(
        sql,
        (value, value, value)
    )

    customers = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "viewcustomers.html",
        customers=customers
    )

@admin.route("/viewtransactions")
@role_required("Administrator", "Manager", "Specialist Officer", "Clerk")
def viewtransactions():

    if "admin_id" not in session:
        return redirect(url_for("admin.adminlogin"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            transaction_id,
            account_number,
            transaction_type,
            amount,
            transaction_date,
            transaction_time,
            remarks,
            status
        FROM transactions
        ORDER BY transaction_id DESC
    """)

    transactions = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "viewtransactions.html",
        transactions=transactions
    )

@admin.route("/approveloan/<int:id>")
@role_required("Administrator", "Manager")
def approveloan(id):

    conn = get_db_connection()

    cursor = conn.cursor()

    cursor.execute(
        "UPDATE loan_application SET loan_status='Approved' WHERE loan_id=%s",
        (id,)
    )

    conn.commit()

    cursor.close()
    conn.close()

    flash("Loan Approved Successfully")

    return redirect(url_for("loan.loanapplications"))

@admin.route("/rejectloan/<int:id>")
@role_required("Administrator", "Manager")
def rejectloan(id):

    conn = get_db_connection()

    cursor = conn.cursor()

    cursor.execute(
        "UPDATE loan_application SET loan_status='Rejected' WHERE loan_id=%s",
        (id,)
    )

    conn.commit()

    cursor.close()
    conn.close()

    flash("Loan Rejected Successfully")

    return redirect(url_for("loan.loanapplications"))

@admin.route("/reports")
@role_required("Administrator", "Manager", "Specialist Officer")
def reports():

    if "admin_id" not in session:
        return redirect(url_for("admin.adminlogin"))

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # ==============================
        # DASHBOARD COUNTS
        # ==============================

        cursor.execute("SELECT COUNT(*) AS total FROM customer")
        total_customers = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM account")
        total_accounts = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM transactions")
        total_transactions = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM loan_application")
        total_loans = cursor.fetchone()["total"]

        # ==============================
        # ACTIVE ACCOUNTS
        # ==============================

        try:
            cursor.execute("""
                SELECT COUNT(*) AS total
                FROM account
                WHERE status = 'Active'
            """)
            active_accounts = cursor.fetchone()["total"]
        except Exception:
            active_accounts = total_accounts

        # ==============================
        # LOAN APPROVAL RATE
        # ==============================

        try:
            cursor.execute("""
                SELECT
                    COUNT(*) AS total_loans,
                    SUM(
                        CASE
                            WHEN loan_status = 'Approved'
                            THEN 1
                            ELSE 0
                        END
                    ) AS approved_loans
                FROM loan_application
            """)

            loan_data = cursor.fetchone()

            if loan_data["total_loans"] > 0:
                approval_rate = round(
                    (loan_data["approved_loans"] /
                     loan_data["total_loans"]) * 100,
                    2
                )
            else:
                approval_rate = 0

        except Exception:
            approval_rate = 0

        return render_template(
            "reports.html",
            total_customers=total_customers,
            total_accounts=total_accounts,
            active_accounts=active_accounts,
            total_transactions=total_transactions,
            total_loans=total_loans,
            approval_rate=approval_rate
        )

    except Exception as e:

        print("REPORTS ERROR:", str(e))

        flash(
            "Unable to load reports.",
            "danger"
        )

        return redirect(
            url_for("admin.admindashboard")
        )

    finally:

        if cursor:
            cursor.close()

        if conn:
            conn.close()

@admin.route("/export_report", methods=["GET"])
@role_required("Administrator", "Manager", "Specialist Officer")
def export_report():

    if "admin_id" not in session:
        return redirect(url_for("admin.adminlogin"))

    report_type = request.args.get(
        "report_type",
        "Customer Report"
    )

    selected_date = request.args.get(
        "date",
        ""
    )

    conn = None
    cursor = None

    try:

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # ==========================================
        # REPORT CONFIGURATION
        # ==========================================

        if report_type == "Customer Report":

            query = """
                SELECT *
                FROM customer
                ORDER BY customer_id DESC
            """

            cursor.execute(query)

            rows = cursor.fetchall()

            sheet_name = "Customers"
            file_name = "Customer_Report.xlsx"

        elif report_type == "Account Report":

            query = """
                SELECT *
                FROM account
                ORDER BY account_number
            """

            cursor.execute(query)

            rows = cursor.fetchall()

            sheet_name = "Accounts"
            file_name = "Account_Report.xlsx"

        elif report_type == "Transaction Report":

            query = """
                SELECT *
                FROM transactions
                ORDER BY transaction_id DESC
            """

            cursor.execute(query)

            rows = cursor.fetchall()

            sheet_name = "Transactions"
            file_name = "Transaction_Report.xlsx"

        elif report_type == "Loan Report":

            query = """
                SELECT
                    l.loan_id,
                    l.customer_id,
                    c.full_name,
                    l.loan_type,
                    l.loan_amount,
                    l.monthly_income,
                    l.credit_score,
                    l.employment_type,
                    l.loan_term,
                    l.application_date,
                    l.loan_status
                FROM loan_application l
                LEFT JOIN customer c
                    ON l.customer_id = c.customer_id
                ORDER BY l.loan_id DESC
            """

            cursor.execute(query)

            rows = cursor.fetchall()

            sheet_name = "Loans"
            file_name = "Loan_Report.xlsx"

        elif report_type == "Loan Prediction Report":

            query = """
                SELECT
                    lp.loan_id,
                    c.full_name,
                    l.loan_type,
                    l.loan_amount,
                    l.monthly_income,
                    l.credit_score,
                    l.employment_type,
                    l.loan_term,
                    lp.prediction_result,
                    lp.approval_probability,
                    lp.model_accuracy,
                    lp.prediction_date
                FROM loan_prediction lp
                LEFT JOIN loan_application l
                    ON lp.loan_id = l.loan_id
                LEFT JOIN customer c
                    ON l.customer_id = c.customer_id
                ORDER BY lp.prediction_date DESC
            """

            cursor.execute(query)

            rows = cursor.fetchall()

            sheet_name = "Loan Predictions"
            file_name = "Loan_Prediction_Report.xlsx"

        elif report_type == "Daily Report":

            if selected_date:

                query = """
                    SELECT *
                    FROM transactions
                    WHERE DATE(transaction_date) = %s
                    ORDER BY transaction_id DESC
                """

                cursor.execute(
                    query,
                    (selected_date,)
                )

                file_name = (
                    f"Daily_Transaction_Report_"
                    f"{selected_date}.xlsx"
                )

            else:

                query = """
                    SELECT *
                    FROM transactions
                    WHERE DATE(transaction_date) = CURDATE()
                    ORDER BY transaction_id DESC
                """

                cursor.execute(query)

                file_name = "Daily_Transaction_Report.xlsx"

            rows = cursor.fetchall()

            sheet_name = "Daily Transactions"

        elif report_type == "Weekly Report":

            query = """
                SELECT *
                FROM transactions
                WHERE transaction_date >=
                      DATE_SUB(CURDATE(), INTERVAL 7 DAY)
                ORDER BY transaction_id DESC
            """

            cursor.execute(query)

            rows = cursor.fetchall()

            sheet_name = "Weekly Transactions"
            file_name = "Weekly_Transaction_Report.xlsx"

        elif report_type == "Monthly Report":

            query = """
                SELECT *
                FROM transactions
                WHERE MONTH(transaction_date) = MONTH(CURDATE())
                  AND YEAR(transaction_date) = YEAR(CURDATE())
                ORDER BY transaction_id DESC
            """

            cursor.execute(query)

            rows = cursor.fetchall()

            sheet_name = "Monthly Transactions"
            file_name = "Monthly_Transaction_Report.xlsx"

        elif report_type == "Yearly Report":

            query = """
                SELECT *
                FROM transactions
                WHERE YEAR(transaction_date) = YEAR(CURDATE())
                ORDER BY transaction_id DESC
            """

            cursor.execute(query)

            rows = cursor.fetchall()

            sheet_name = "Yearly Transactions"
            file_name = "Yearly_Transaction_Report.xlsx"

        else:

            flash(
                "Invalid report type.",
                "danger"
            )

            return redirect(
                url_for("admin.reports")
            )

        # ==========================================
        # CREATE EXCEL WORKBOOK
        # ==========================================

        workbook = Workbook()

        worksheet = workbook.active
        worksheet.title = sheet_name[:31]

        # ==========================================
        # TITLE
        # ==========================================

        worksheet["A1"] = "SECURE BANK"
        worksheet["A1"].font = Font(
            bold=True,
            size=16
        )

        worksheet["A2"] = report_type
        worksheet["A2"].font = Font(
            bold=True,
            size=13
        )

        worksheet["A3"] = (
            "Generated Date: "
            + datetime.now().strftime(
                "%d-%m-%Y %H:%M:%S"
            )
        )

        # ==========================================
        # HEADERS
        # ==========================================

        if rows:

            columns = list(rows[0].keys())

            header_row = 5

            for col_index, column_name in enumerate(
                columns,
                start=1
            ):

                cell = worksheet.cell(
                    row=header_row,
                    column=col_index
                )

                cell.value = column_name.replace(
                    "_",
                    " "
                ).title()

                cell.font = Font(
                    bold=True
                )

                cell.alignment = Alignment(
                    horizontal="center"
                )

            # ======================================
            # DATA
            # ======================================

            for row_index, row in enumerate(
                rows,
                start=header_row + 1
            ):

                for col_index, column_name in enumerate(
                    columns,
                    start=1
                ):

                    cell = worksheet.cell(
                        row=row_index,
                        column=col_index
                    )

                    cell.value = row[column_name]

        else:

            worksheet["A5"] = "No records found."
            worksheet["A5"].font = Font(
                bold=True
            )

        # ==========================================
        # AUTO COLUMN WIDTH
        # ==========================================

        for column in worksheet.columns:

            max_length = 0

            column_letter = column[0].column_letter

            for cell in column:

                if cell.value is not None:

                    length = len(
                        str(cell.value)
                    )

                    if length > max_length:
                        max_length = length

            worksheet.column_dimensions[
                column_letter
            ].width = min(
                max_length + 3,
                40
            )

        # ==========================================
        # SAVE REPORT IN PROJECT FOLDER
        # ==========================================

        report_folder = os.path.join(
            os.getcwd(),
            "generated_reports"
        )

        os.makedirs(
            report_folder,
            exist_ok=True
        )

        report_path = os.path.join(
            report_folder,
            file_name
        )

        workbook.save(report_path)

        # ==========================================
        # DOWNLOAD EXCEL FILE
        # ==========================================

        output = BytesIO()

        workbook.save(output)

        output.seek(0)

        return send_file(
            output,
            as_attachment=True,
            download_name=file_name,
            mimetype=(
                "application/vnd.openxmlformats-"
                "officedocument.spreadsheetml.sheet"
            )
        )

    except Exception as e:

        print(
            "EXCEL REPORT ERROR:",
            str(e)
        )

        flash(
            "Unable to generate Excel report: "
            + str(e),
            "danger"
        )

        return redirect(
            url_for("admin.reports")
        )

    finally:

        if cursor:
            cursor.close()

        if conn:
            conn.close()
                        
@admin.route("/statistics")
@role_required("Administrator", "Manager")
def statistics():

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Total customers
    cursor.execute("""
        SELECT COUNT(*) AS total_customers
        FROM customer
    """)
    total_customers = cursor.fetchone()["total_customers"]

    # Total loan applications
    cursor.execute("""
        SELECT COUNT(*) AS total_loans
        FROM loan_application
    """)
    total_loans = cursor.fetchone()["total_loans"]

    # Pending loans
    cursor.execute("""
        SELECT COUNT(*) AS pending_loans
        FROM loan_application
        WHERE loan_status = 'Pending'
    """)
    pending_loans = cursor.fetchone()["pending_loans"]

    # Approved loans
    cursor.execute("""
        SELECT COUNT(*) AS approved_loans
        FROM loan_application
        WHERE loan_status = 'Approved'
    """)
    approved_loans = cursor.fetchone()["approved_loans"]

    # Rejected loans
    cursor.execute("""
        SELECT COUNT(*) AS rejected_loans
        FROM loan_application
        WHERE loan_status = 'Rejected'
    """)
    rejected_loans = cursor.fetchone()["rejected_loans"]

    # Total approved loan amount
    cursor.execute("""
        SELECT COALESCE(SUM(loan_amount), 0) AS approved_amount
        FROM loan_application
        WHERE loan_status = 'Approved'
    """)
    approved_amount = cursor.fetchone()["approved_amount"]

    cursor.close()
    conn.close()

    return render_template(
        "statistics.html",
        total_customers=total_customers,
        total_loans=total_loans,
        pending_loans=pending_loans,
        approved_loans=approved_loans,
        rejected_loans=rejected_loans,
        approved_amount=approved_amount
    )

@admin.route("/adminlogout")
def adminlogout():

    session.clear()

    flash("Admin Logged Out Successfully")

    return redirect(url_for("admin.adminlogin"))

@admin.route("/loan-applications/<status>")
@role_required("Administrator", "Manager", "Specialist Officer", "Clerk")
def loan_applications(status):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if status == "all":
        cursor.execute("""
            SELECT 
                la.*,
                c.full_name
            FROM loan_application la
            JOIN customer c
                ON la.customer_id = c.customer_id
            ORDER BY la.loan_id DESC
        """)

    else:
        cursor.execute("""
            SELECT 
                la.*,
                c.full_name
            FROM loan_application la
            JOIN customer c
                ON la.customer_id = c.customer_id
            WHERE la.loan_status = %s
            ORDER BY la.loan_id DESC
        """, (status,))

    applications = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template(
        "loan_applications.html",
        applications=applications,
        status=status
    )
