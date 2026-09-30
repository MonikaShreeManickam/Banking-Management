from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from db import get_db_connection
from werkzeug.utils import secure_filename
from loan_model import predict_loan, MODEL_ACCURACY

import loan_model

print("========================================")
print("LOAN MODEL FILE:", loan_model.__file__)
print("MODEL ACCURACY:", MODEL_ACCURACY)
print("========================================")

from admin import role_required

import os
import uuid

from PIL import Image, ImageStat, ImageOps, ImageFilter

import re
import unicodedata
from difflib import SequenceMatcher

try:
    import pytesseract
except ImportError:
    pytesseract = None

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None


loan = Blueprint("loan", __name__)


# =========================================================
# FILE UPLOAD SETTINGS
# =========================================================

ALLOWED_DOCUMENT_EXTENSIONS = {
    "pdf",
    "jpg",
    "jpeg",
    "png"
}

ALLOWED_IMAGE_EXTENSIONS = {
    "jpg",
    "jpeg",
    "png"
}


def allowed_file(filename, allowed_extensions):

    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in allowed_extensions
    )


def create_unique_filename(filename):

    extension = filename.rsplit(".", 1)[1].lower()

    return f"{uuid.uuid4().hex}.{extension}"


# =========================================================
# OCR - CUSTOMER NAME VERIFICATION
# =========================================================

def normalize_name(name):
    if not name:
        return ""
    name = unicodedata.normalize("NFKD", str(name)).upper()
    name = re.sub(r"[^\w\s]", " ", name, flags=re.UNICODE)
    return re.sub(r"\s+", " ", name).strip()


def names_match(registered_name, ocr_text):
    registered = normalize_name(registered_name)
    extracted = normalize_name(ocr_text)
    if not registered or not extracted:
        return False
    if registered == extracted:
        return True

    registered_tokens = set(registered.split())
    extracted_tokens = set(extracted.split())
    if registered_tokens and registered_tokens.issubset(extracted_tokens):
        return True

    return SequenceMatcher(None, registered, extracted).ratio() >= 0.88


def extract_name_from_ocr_text(text):
    if not text:
        return ""

    lines = [
        re.sub(r"\s+", " ", line).strip()
        for line in text.splitlines()
        if line.strip()
    ]

    patterns = [
        r"(?:NAME|N4ME)\s*[:\-]?\s*(.+)",
        r"(?:नाम)\s*[:\-]?\s*(.+)"
    ]

    for line in lines:
        for pattern in patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                value = re.sub(r"[^\w\s]", " ", match.group(1), flags=re.UNICODE)
                value = re.sub(r"\s+", " ", value).strip()
                if len(value) >= 2:
                    return value

    return " ".join(lines)


def extract_name_from_document(file, extension):
    if pytesseract is None:
        raise RuntimeError("pytesseract is not installed.")

    file.stream.seek(0)

    if extension in {"jpg", "jpeg", "png"}:
        image = Image.open(file.stream)
        image = ImageOps.exif_transpose(image).convert("RGB")
        image = image.resize((image.width * 2, image.height * 2))
        image = ImageOps.grayscale(image)
        image = ImageOps.autocontrast(image)
        image = image.filter(ImageFilter.SHARPEN)
        text = pytesseract.image_to_string(image, config="--psm 6")
        file.stream.seek(0)
        return extract_name_from_ocr_text(text)

    if extension == "pdf":
        if fitz is None:
            raise RuntimeError("PyMuPDF is not installed.")

        pdf = fitz.open(stream=file.stream.read(), filetype="pdf")
        all_text = []
        try:
            for page in pdf:
                page_text = page.get_text("text")
                if not page_text.strip():
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    image = ImageOps.grayscale(image)
                    image = ImageOps.autocontrast(image)
                    image = image.filter(ImageFilter.SHARPEN)
                    page_text = pytesseract.image_to_string(image, config="--psm 6")
                all_text.append(page_text)
        finally:
            pdf.close()

        file.stream.seek(0)
        return extract_name_from_ocr_text("\n".join(all_text))

    file.stream.seek(0)
    return ""


# =========================================================
# IMAGE QUALITY VERIFICATION
# =========================================================

def verify_image_quality(file):

    try:
        file.stream.seek(0)
        image = Image.open(file.stream)
        image.load()
        width, height = image.size

        if width < 800 or height < 600:
            return False, (
                "Image resolution is too low. "
                "Please upload a clearer image with at least 800 x 600 pixels."
            )

        rgb_image = image.convert("RGB")
        stat = ImageStat.Stat(rgb_image)
        average_brightness = sum(stat.mean) / 3

        if average_brightness < 55:
            return False, "Image is too dark. Please capture the image in better lighting."

        if average_brightness > 235:
            return False, "Image is too bright. Please avoid strong light or reflection."

        gray = rgb_image.convert("L")
        small_width = 100
        ratio = small_width / gray.width
        small_height = max(1, int(gray.height * ratio))
        small = gray.resize((small_width, small_height))
        pixels = list(small.getdata())
        dark_pixels = sum(1 for pixel in pixels if pixel < 35)
        dark_percentage = (dark_pixels / len(pixels)) * 100

        if dark_percentage > 45:
            return False, "Strong shadow detected. Please remove shadows and capture the image again."

        sharp_image = gray.resize((300, max(1, int(gray.height * 300 / gray.width))))
        pixels = list(sharp_image.getdata())
        if len(pixels) < 10:
            return False, "Unable to verify image quality."

        differences = []
        width_small, height_small = sharp_image.size
        for y in range(height_small - 1):
            for x in range(width_small - 1):
                current = pixels[y * width_small + x]
                right = pixels[y * width_small + x + 1]
                differences.append(abs(current - right))

        average_difference = sum(differences) / len(differences)

        if average_difference < 3:
            return False, "Image appears blurry. Please keep the camera steady and capture a sharper image."

        return True, "Image quality verified successfully."

    except Exception as e:
        print("Image Verification Error:", e)
        return False, "Unable to verify the image. Please upload a valid image."

    finally:
        try:
            file.stream.seek(0)
        except Exception:
            pass


# =========================================================
# CREDIT SCORE - MAXIMUM ELIGIBLE LOAN AMOUNT
# =========================================================

def get_max_loan_amount(credit_score):

    if credit_score >= 750:
        return 1000000       # ₹10 Lakhs

    elif credit_score >= 700:
        return 700000        # ₹7 Lakhs

    elif credit_score >= 650:
        return 500000        # ₹5 Lakhs

    elif credit_score >= 600:
        return 300000        # ₹3 Lakhs

    else:
        return 0

def validate_loan_conditions(loan_amount, monthly_income,
                             credit_score, loan_term):

    try:
        loan_amount = float(loan_amount)
        monthly_income = float(monthly_income)
        credit_score = int(credit_score)
        loan_term = int(loan_term)
    except (ValueError, TypeError):

        return False, "Invalid loan details."

    # Monthly income
    if monthly_income <= 0:
        return False, "Monthly income must be greater than ₹0."

    # Loan amount
    if loan_amount <= 0:
        return False, "Loan amount must be greater than ₹0."

    # Loan term
    if loan_term <= 0:
        return False, "Loan term must be greater than 0 months."

    # Credit score range
    if credit_score < 300 or credit_score > 900:
        return False, "Invalid credit score."

    # Maximum amount according to credit score
    max_amount = get_max_loan_amount(credit_score)

    if max_amount <= 0:
        return False, (
            "Your credit score is too low. "
            "You are not eligible for a loan."
        )

    if loan_amount > max_amount:
        return False, (
            f"Your credit score allows a maximum loan "
            f"amount of ₹{max_amount:,.2f}."
        )

    return True, ""

# =========================================================
# APPLY LOAN - CUSTOMER
# =========================================================

@loan.route("/applyloan", methods=["GET", "POST"])
def applyloan():

    # -----------------------------------------------------
    # CUSTOMER LOGIN CHECK
    # -----------------------------------------------------

    if "customer_id" not in session:
        return redirect(url_for("customer.dashboard"))

    if request.method == "POST":

        customer_id = session["customer_id"]

        conn = None
        cursor = None

        try:

            # =================================================
            # GET FORM DATA
            # =================================================

            loan_type = request.form.get("loan_type")

            loan_amount = float(
                request.form.get("loan_amount", 0)
            )

            monthly_income = float(
                request.form.get("monthly_income", 0)
            )

            credit_score = int(
                request.form.get("credit_score", 0)
            )

            employment_type = request.form.get(
                "employment_type"
            )

            loan_term = int(
                request.form.get("loan_term", 0)
            )

            document_type = request.form.get(
                "document_type"
            )


            # =================================================
            # ALLOWED VALUES
            # =================================================

            allowed_loan_types = [
                "Home Loan",
                "Personal Loan",
                "Vehicle Loan",
                "Education Loan",
                "Business Loan"
            ]

            allowed_employment_types = [
                "Salaried",
                "Self Employed",
                "Business",
                "Government"
            ]

            allowed_documents = [
                "Aadhaar",
                "PAN Card",
                "Voter ID"
            ]


            # =================================================
            # BASIC VALIDATION
            # =================================================

            if loan_type not in allowed_loan_types:

                flash(
                    "Please select a valid loan type.",
                    "error"
                )

                return redirect(
                    url_for("loan.applyloan")
                )


            if employment_type not in allowed_employment_types:

                flash(
                    "Please select a valid employment type.",
                    "error"
                )

                return redirect(
                    url_for("loan.applyloan")
                )


            if loan_amount <= 0:

                flash(
                    "Loan amount must be greater than zero.",
                    "error"
                )

                return redirect(
                    url_for("loan.applyloan")
                )


            if monthly_income <= 0:

                flash(
                    "Monthly income must be greater than zero.",
                    "error"
                )

                return redirect(
                    url_for("loan.applyloan")
                )


            if loan_term <= 0:

                flash(
                    "Loan term must be greater than zero.",
                    "error"
                )

                return redirect(
                    url_for("loan.applyloan")
                )


            if credit_score < 300 or credit_score > 900:

                flash(
                    "Credit score must be between 300 and 900.",
                    "error"
                )

                return redirect(
                    url_for("loan.applyloan")
                )


            # =================================================
            # CREDIT SCORE - MAXIMUM LOAN AMOUNT
            # =================================================

            max_loan_amount = get_max_loan_amount(
                credit_score
            )


            if max_loan_amount == 0:

                flash(
                    "Your credit score is too low. "
                    "You are not eligible for a loan.",
                    "error"
                )

                return redirect(
                    url_for("loan.applyloan")
                )


            if loan_amount > max_loan_amount:

                flash(
                    f"Your credit score allows a maximum "
                    f"loan amount of ₹{max_loan_amount:,.0f}.",
                    "error"
                )

                return redirect(
                    url_for("loan.applyloan")
                )


            # =================================================
            # IDENTITY DOCUMENT VALIDATION
            # =================================================

            if document_type not in allowed_documents:

                flash(
                    "Please select a valid identity document.",
                    "error"
                )

                return redirect(
                    url_for("loan.applyloan")
                )


            document = request.files.get(
                "document"
            )


            if not document or document.filename == "":

                flash(
                    "Please upload your identity document.",
                    "error"
                )

                return redirect(
                    url_for("loan.applyloan")
                )


            # =================================================
            # DOCUMENT FILE TYPE VALIDATION
            # =================================================

            if not allowed_file(
                document.filename,
                ALLOWED_DOCUMENT_EXTENSIONS
            ):

                flash(
                    "Invalid document format. "
                    "Allowed formats: PDF, JPG, JPEG, PNG.",
                    "error"
                )

                return redirect(
                    url_for("loan.applyloan")
                )


            document_extension = (
                document.filename
                .rsplit(".", 1)[1]
                .lower()
            )


            # =================================================
            # IMAGE QUALITY VERIFICATION
            # =================================================

            if document_extension in {
                "jpg",
                "jpeg",
                "png"
            }:

                image_ok, image_message = (
                    verify_image_quality(document)
                )


                if not image_ok:

                    flash(
                        "Identity document verification failed: "
                        + image_message,
                        "error"
                    )

                    return redirect(
                        url_for("loan.applyloan")
                    )


            # =================================================
            # CREATE DOCUMENT FOLDER
            # =================================================

            document_folder = os.path.join(
                "static",
                "uploads",
                "loan_documents"
            )


            os.makedirs(
                document_folder,
                exist_ok=True
            )


            # =================================================
            # SAVE IDENTITY DOCUMENT
            # =================================================

            document_filename = create_unique_filename(
                secure_filename(
                    document.filename
                )
            )


            document_path = os.path.join(
                document_folder,
                document_filename
            )


            document.save(
                document_path
            )


            # Database-relative path

            document_db_path = os.path.join(
                "uploads",
                "loan_documents",
                document_filename
            ).replace("\\", "/")


            # =================================================
            # DOCUMENT TYPE COLUMN MAPPING
            # =================================================

            aadhaar_document = None
            pan_document = None
            voter_document = None


            if document_type == "Aadhaar":

                aadhaar_document = document_db_path


            elif document_type == "PAN Card":

                pan_document = document_db_path


            elif document_type == "Voter ID":

                voter_document = document_db_path


            # =================================================
            # PROPERTY / VEHICLE IMAGE
            # =================================================

            property_image_db_path = None


            if loan_type in [
                "Home Loan",
                "Vehicle Loan"
            ]:

                property_image = request.files.get(
                    "property_image"
                )


                # -------------------------------------------------
                # CHECK IMAGE
                # -------------------------------------------------

                if (
                    not property_image
                    or property_image.filename == ""
                ):

                    if loan_type == "Home Loan":

                        flash(
                            "Please upload the property image.",
                            "error"
                        )

                    else:

                        flash(
                            "Please upload the vehicle image.",
                            "error"
                        )


                    return redirect(
                        url_for("loan.applyloan")
                    )


                # -------------------------------------------------
                # IMAGE FORMAT
                # -------------------------------------------------

                if not allowed_file(
                    property_image.filename,
                    ALLOWED_IMAGE_EXTENSIONS
                ):

                    flash(
                        "Invalid image format. "
                        "Allowed formats: JPG, JPEG, PNG.",
                        "error"
                    )

                    return redirect(
                        url_for("loan.applyloan")
                    )


                # -------------------------------------------------
                # IMAGE QUALITY
                # -------------------------------------------------

                image_ok, image_message = (
                    verify_image_quality(property_image)
                )


                if not image_ok:

                    if loan_type == "Home Loan":

                        flash(
                            "Property image verification failed: "
                            + image_message,
                            "error"
                        )

                    else:

                        flash(
                            "Vehicle image verification failed: "
                            + image_message,
                            "error"
                        )


                    return redirect(
                        url_for("loan.applyloan")
                    )


                # -------------------------------------------------
                # CREATE IMAGE FOLDER
                # -------------------------------------------------

                image_folder = os.path.join(
                    "static",
                    "uploads",
                    "loan_properties"
                )


                os.makedirs(
                    image_folder,
                    exist_ok=True
                )


                # -------------------------------------------------
                # SAVE PROPERTY / VEHICLE IMAGE
                # -------------------------------------------------

                image_filename = create_unique_filename(
                    secure_filename(
                        property_image.filename
                    )
                )


                image_path = os.path.join(
                    image_folder,
                    image_filename
                )


                property_image.save(
                    image_path
                )


                # Database-relative path

                property_image_db_path = os.path.join(
                    "uploads",
                    "loan_properties",
                    image_filename
                ).replace("\\", "/")


            # =================================================
            # DATABASE CONNECTION
            # =================================================

            conn = get_db_connection()

            cursor = conn.cursor()


            # =================================================
            # INSERT LOAN APPLICATION
            # =================================================

            cursor.execute(
                """
                INSERT INTO loan_application
                (
                    customer_id,
                    loan_type,
                    loan_amount,
                    monthly_income,
                    credit_score,
                    employment_type,
                    loan_term,
                    document_path,
                    aadhaar_document,
                    pan_document,
                    voter_document,
                    property_image,
                    application_date,
                    loan_status
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    CURDATE(),
                    'Pending'
                )
                """,
                (
                    customer_id,
                    loan_type,
                    loan_amount,
                    monthly_income,
                    credit_score,
                    employment_type,
                    loan_term,
                    document_db_path,
                    aadhaar_document,
                    pan_document,
                    voter_document,
                    property_image_db_path
                )
            )


            # =================================================
            # COMMIT
            # =================================================

            conn.commit()


            # =================================================
            # CLOSE DATABASE
            # =================================================

            cursor.close()
            conn.close()

            cursor = None
            conn = None


            # =================================================
            # SUCCESS MESSAGE
            # =================================================

            flash(
                "Loan Application Submitted Successfully.",
                "success"
            )


            # =================================================
            # REDIRECT TO LOAN STATUS
            # =================================================

            return redirect(
                url_for("loan.loanstatus")
            )


        # =====================================================
        # INVALID NUMERIC VALUE
        # =====================================================

        except ValueError:

            if cursor:
                cursor.close()

            if conn:
                conn.close()


            flash(
                "Please enter valid numeric values.",
                "error"
            )


            return redirect(
                url_for("loan.applyloan")
            )


        # =====================================================
        # DATABASE / OTHER ERROR
        # =====================================================

        except Exception as e:

            print(
                "Apply Loan Error:",
                e
            )


            if cursor:

                try:
                    cursor.close()
                except:
                    pass


            if conn:

                try:
                    conn.close()
                except:
                    pass


            flash(
                "Unable to submit loan application.",
                "error"
            )


            return redirect(
                url_for("loan.applyloan")
            )


    # =========================================================
    # GET REQUEST
    # =========================================================

    return render_template(
        "applyloan.html"
    )

# =========================================================
# CUSTOMER LOAN STATUS
# =========================================================

@loan.route("/loanstatus")
def loanstatus():

    if "customer_id" not in session:

        return redirect(
            url_for("customer.dashboard")
        )


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
        (
            session["customer_id"],
        )
    )


    loans = cursor.fetchall()


    cursor.close()
    conn.close()


    return render_template(
        "loanstatus.html",
        loans=loans
    )


# =========================================================
# LOAN DETAILS
# =========================================================

@loan.route("/loandetails/<int:id>")
def loandetails(id):

    if "customer_id" not in session:

        return redirect(
            url_for("customer.dashboard")
        )


    conn = get_db_connection()

    cursor = conn.cursor(
        dictionary=True
    )


    # Customer can view only their own loan
    cursor.execute(
        """
        SELECT *
        FROM loan_application
        WHERE loan_id=%s
        AND customer_id=%s
        """,
        (
            id,
            session["customer_id"]
        )
    )


    loan_details = cursor.fetchone()


    cursor.close()
    conn.close()


    if not loan_details:

        flash(
            "Loan application not found."
        )

        return redirect(
            url_for("loan.loanstatus")
        )


    return render_template(
        "loandetails.html",
        loan=loan_details
    )


# =========================================================
# ADMIN LOAN PREDICTION
# =========================================================

@loan.route(
    "/loanprediction/<int:loan_id>",
    methods=["GET", "POST"]
)
@role_required("Administrator", "Manager", "Specialist Officer")
def loanprediction(loan_id):

    conn = get_db_connection()

    cursor = conn.cursor(
        dictionary=True
    )

    # -----------------------------------------------------
    # GET LOAN + CUSTOMER DETAILS
    # -----------------------------------------------------

    cursor.execute(
        """
        SELECT
            l.*,
            c.full_name
        FROM loan_application l
        LEFT JOIN customer c
            ON l.customer_id = c.customer_id
        WHERE l.loan_id=%s
        """,
        (
            loan_id,
        )
    )

    loan_details = cursor.fetchone()

    if not loan_details:

        cursor.close()
        conn.close()

        flash(
            "Loan application not found."
        )

        return redirect(
            url_for("loan.loanapplications")
        )

    prediction = None
    probability = 0

    max_loan_amount = get_max_loan_amount(
        loan_details["credit_score"]
    )

    # -----------------------------------------------------
    # RUN ML PREDICTION
    # -----------------------------------------------------

    if request.method == "POST":
        try:
            # -------------------------------------------------
            # RUN MACHINE LEARNING PREDICTION
            # -------------------------------------------------
            print("========================================")
            print("VALUES SENT TO ML")
            print("Credit Score:", loan_details["credit_score"])
            print("Monthly Income:", loan_details["monthly_income"])
            print("Loan Amount:", loan_details["loan_amount"])
            print("Employment Type:", loan_details["employment_type"])
            print("Loan Term:", loan_details["loan_term"])
            print("Loan Type:", loan_details["loan_type"])
            print("========================================")
            prediction, probability = predict_loan(
                loan_details["credit_score"],
                loan_details["monthly_income"],
                loan_details["loan_amount"],
                loan_details["employment_type"],
                loan_details["loan_term"],
                loan_details["loan_type"]
            )

            print("========================================")
            print("ML PREDICTION RESULT")
            print("Prediction:", prediction)
            print("Probability:", probability)
            print("========================================")
            # -------------------------------------------------
            # CREDIT SCORE ELIGIBILITY
            # -------------------------------------------------
            if max_loan_amount == 0:
                prediction = "Rejected"
                probability = 0
                flash(
                    "Credit score is too low "
                    "for loan eligibility."
                )
            # -------------------------------------------------
            # MAXIMUM LOAN AMOUNT CHECK
            # -------------------------------------------------
            elif float(loan_details["loan_amount"]) > float(max_loan_amount):
                prediction = "Rejected"
                probability = 0
                flash(
                    f"Loan amount exceeds the "
                    f"maximum eligible amount of "
                    f"₹{max_loan_amount:,.0f}."
                )
            # -------------------------------------------------
            # ML RECOMMENDATION IS VALID
            # -------------------------------------------------
            else:
                if prediction == "Approved":
                    flash(
                        f"ML Recommendation: Approved "
                        f"with {probability:.2f}% approval probability."
                        )
                else:
                    flash(
                        f"ML Recommendation: Rejected "
                        f"with {probability:.2f}% approval probability."
                    )

        except Exception as e:
            print("Loan Prediction Error:", repr(e))
            flash(
            f"Unable to generate loan prediction: {str(e)}"
            )

    # -----------------------------------------------------
    # CLOSE DATABASE CONNECTION
    # -----------------------------------------------------

    cursor.close()
    conn.close()

    # -----------------------------------------------------
    # DISPLAY PREDICTION PAGE
    # -----------------------------------------------------

    return render_template(
        "loanprediction.html",
        loan=loan_details,
        prediction=prediction,
        probability=probability,
        max_loan_amount=max_loan_amount,
        model_accuracy=MODEL_ACCURACY
    )

# =========================================================
# SAVE LOAN PREDICTION
# =========================================================

@loan.route("/saveprediction", methods=["POST"])
@role_required("Administrator", "Manager", "Specialist Officer")
def saveprediction():

    connection = None
    cursor = None

    try:

        loan_id = request.form.get("loan_id")

        if not loan_id:

            flash("Loan ID is required.", "danger")

            return redirect(
                url_for("loan.loanapplications")
            )


        connection = get_db_connection()

        cursor = connection.cursor(dictionary=True)


        # ==================================================
        # GET CURRENT LOAN DETAILS
        # ==================================================

        cursor.execute("""
            SELECT
                l.loan_id,
                l.customer_id,
                l.loan_type,
                l.loan_amount,
                l.monthly_income,
                l.credit_score,
                l.employment_type,
                l.loan_term,
                l.loan_status,
                c.full_name
            FROM loan_application l
            JOIN customer c
                ON l.customer_id = c.customer_id
            WHERE l.loan_id = %s
        """, (loan_id,))

        loan_data = cursor.fetchone()


        if not loan_data:

            flash(
                "Loan application not found.",
                "danger"
            )

            return redirect(
                url_for("loan.loanapplications")
            )


        # ==================================================
        # ONLY PENDING APPLICATION CAN HAVE NEW PREDICTION
        # ==================================================

        if loan_data["loan_status"] != "Pending":

            flash(
                "Prediction cannot be saved because "
                "this loan application is already processed.",
                "warning"
            )

            return redirect(
                url_for(
                    "loan.loanprediction",
                    loan_id=loan_id
                )
            )


        # ==================================================
        # CHECK ELIGIBILITY CONDITIONS AGAIN
        # ==================================================

        eligible, error_message = validate_loan_conditions(
            loan_data["loan_amount"],
            loan_data["monthly_income"],
            loan_data["credit_score"],
            loan_data["loan_term"]
        )


        if not eligible:

            flash(error_message, "danger")

            return redirect(
                url_for(
                    "loan.loanprediction",
                    loan_id=loan_id
                )
            )


        # ==================================================
        # RUN ML MODEL AGAIN ON SERVER
        # ==================================================

        prediction_result, approval_probability = predict_loan(

            loan_data["credit_score"],

            loan_data["monthly_income"],

            loan_data["loan_amount"],

            loan_data["employment_type"],

            loan_data["loan_term"],

            loan_data["loan_type"]

        )


        # Convert numpy value to Python float
        approval_probability = float(
            approval_probability
        )


        # ==================================================
        # CREDIT SCORE MAXIMUM LOAN CHECK
        # ==================================================

        max_loan_amount = get_max_loan_amount(
            loan_data["credit_score"]
        )


        if max_loan_amount <= 0:

            prediction_result = "Rejected"

            approval_probability = 0.0


        elif float(loan_data["loan_amount"]) > max_loan_amount:

            prediction_result = "Rejected"

            approval_probability = 0.0


        # ==================================================
        # SAVE SERVER-CALCULATED PREDICTION
        # ==================================================

        cursor.execute("""
            INSERT INTO loan_prediction
            (
                loan_id,
                prediction_result,
                approval_probability,
                model_accuracy,
                prediction_date
            )
            VALUES
            (
                %s,
                %s,
                %s,
                %s,
                CURDATE()
            )
        """, (
            loan_id,
            prediction_result,
            approval_probability,
            MODEL_ACCURACY
        ))


        connection.commit()


        flash(
            "Loan Prediction Saved Successfully.",
            "success"
        )


        # ==================================================
        # SHOW SAVED PREDICTION HISTORY
        # ==================================================

        return redirect(
            url_for("loan.loanpredictionhistory")
        )


    except Exception as e:

        if connection:
            connection.rollback()

        print(
            "SAVE PREDICTION ERROR:",
            str(e)
        )

        flash(
            "Unable to save loan prediction.",
            "danger"
        )

        return redirect(
            url_for("loan.loanapplications")
        )


    finally:

        if cursor:
            cursor.close()

        if connection:
            connection.close()

@loan.route("/loanpredictionhistory")
@role_required("Administrator", "Manager", "Specialist Officer")
def loanpredictionhistory():

    connection = None
    cursor = None

    try:

        connection = get_db_connection()

        cursor = connection.cursor(dictionary=True)


        cursor.execute("""
            SELECT
                lp.loan_id,
                lp.prediction_result,
                lp.approval_probability,
                lp.model_accuracy,
                lp.prediction_date,

                l.loan_type,
                l.loan_amount,
                l.monthly_income,
                l.credit_score,
                l.employment_type,
                l.loan_term,
                l.loan_status,

                c.full_name

            FROM loan_prediction lp

            JOIN loan_application l
                ON lp.loan_id = l.loan_id

            JOIN customer c
                ON l.customer_id = c.customer_id

            ORDER BY
                lp.prediction_date DESC,
                lp.loan_id DESC
        """)

        predictions = cursor.fetchall()


        return render_template(
            "loanpredictionhistory.html",
            predictions=predictions
        )


    except Exception as e:

        print(
            "PREDICTION HISTORY ERROR:",
            str(e)
        )

        flash(
            "Unable to load prediction history.",
            "danger"
        )

        return redirect(
            url_for("loan.loanapplications")
        )


    finally:

        if cursor:
            cursor.close()

        if connection:
            connection.close()

# =========================================================
# UPDATE LOAN STATUS
# =========================================================
@loan.route(
    "/updateloanstatus/<int:id>/<status>",
    methods=["POST"]
)
@role_required("Administrator", "Manager")
def updateloanstatus(id, status):

    connection = None
    cursor = None

    try:

        # Only these final decisions are allowed
        allowed_statuses = [
            "Approved",
            "Rejected"
        ]

        if status not in allowed_statuses:

            flash(
                "Invalid loan status.",
                "danger"
            )

            return redirect(
                url_for("loan.loanapplications")
            )


        connection = get_db_connection()

        cursor = connection.cursor(dictionary=True)


        # ==================================================
        # GET LOAN
        # ==================================================

        cursor.execute("""
            SELECT
                loan_id,
                customer_id,
                loan_type,
                loan_amount,
                monthly_income,
                credit_score,
                employment_type,
                loan_term,
                loan_status
            FROM loan_application
            WHERE loan_id = %s
        """, (id,))

        loan_data = cursor.fetchone()


        if not loan_data:

            flash(
                "Loan application not found.",
                "danger"
            )

            return redirect(
                url_for("loan.loanapplications")
            )


        # ==================================================
        # ONLY PENDING APPLICATION CAN BE PROCESSED
        # ==================================================

        if loan_data["loan_status"] != "Pending":

            flash(
                "This loan application has already been processed.",
                "warning"
            )

            return redirect(
                url_for("loan.loanapplications")
            )


        # ==================================================
        # REJECT
        # ==================================================

        if status == "Rejected":

            cursor.execute("""
                UPDATE loan_application
                SET loan_status = 'Rejected'
                WHERE loan_id = %s
            """, (id,))

            connection.commit()

            flash(
                "Loan Application Rejected Successfully.",
                "success"
            )

            return redirect(
                url_for("loan.loanapplications")
            )


        # ==================================================
        # APPROVAL VALIDATION
        # ==================================================

        eligible, error_message = validate_loan_conditions(

            loan_data["loan_amount"],

            loan_data["monthly_income"],

            loan_data["credit_score"],

            loan_data["loan_term"]

        )


        if not eligible:

            flash(
                "Approval blocked: " + error_message,
                "danger"
            )

            return redirect(
                url_for("loan.loanapplications")
            )


        # ==================================================
        # GET LATEST SAVED PREDICTION
        # ==================================================

        cursor.execute("""
            SELECT
                prediction_result,
                approval_probability,
                model_accuracy,
                prediction_date

            FROM loan_prediction

            WHERE loan_id = %s

            ORDER BY prediction_date DESC

            LIMIT 1
        """, (id,))

        prediction = cursor.fetchone()


        # ==================================================
        # PREDICTION MUST EXIST
        # ==================================================

        if not prediction:

            flash(
                "Approval blocked. "
                "ML Loan Prediction has not been saved yet.",
                "danger"
            )

            return redirect(
                url_for("loan.loanapplications")
            )


        # ==================================================
        # ML PREDICTION MUST BE APPROVED
        # ==================================================

        if prediction["prediction_result"] != "Approved":

            flash(
                "Approval blocked. "
                "ML Prediction is Rejected.",
                "danger"
            )

            return redirect(
                url_for("loan.loanapplications")
            )


        # ==================================================
        # APPROVE LOAN
        # ==================================================

        cursor.execute("""
            UPDATE loan_application
            SET
                loan_status = 'Approved',
                approved_by = %s
            WHERE loan_id = %s
        """, (
            session.get("admin_id"),
            id
        ))


        connection.commit()


        flash(
            "Loan Application Approved Successfully.",
            "success"
        )


        return redirect(
            url_for("loan.loanapplications")
        )


    except Exception as e:

        if connection:
            connection.rollback()

        print(
            "UPDATE LOAN STATUS ERROR:",
            str(e)
        )

        flash(
            "Unable to update loan status.",
            "danger"
        )

        return redirect(
            url_for("loan.loanapplications")
        )


    finally:

        if cursor:
            cursor.close()

        if connection:
            connection.close()

# =========================================================
# CANCEL LOAN - CUSTOMER
# =========================================================
@loan.route(
    "/cancelloan/<int:id>"
)
def cancelloan(id):
    if "customer_id" not in session:
        return redirect(
            url_for("customer.dashboard")
        )
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        DELETE FROM loan_application
        WHERE loan_id=%s
        AND customer_id=%s
        AND loan_status='Pending'
        """,
        (
            id,
            session["customer_id"]
        )
    )
    conn.commit()
    cursor.close()
    conn.close()
    flash(
        "Loan Application Cancelled Successfully."
    )
    return redirect(
        url_for("loan.loanstatus")
    )
# =========================================================
# LOAN REPORT - CUSTOMER
# =========================================================
@loan.route("/loanreport")
def loanreport():
    if "customer_id" not in session:
        return redirect(
            url_for("customer.dashboard")
        )
    conn = get_db_connection()
    cursor = conn.cursor(
        dictionary=True
    )
    cursor.execute(
        """
        SELECT *
        FROM loan_application
        WHERE customer_id=%s
        ORDER BY application_date DESC
        """,
        (
            session["customer_id"],
        )
    )
    reports = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template(
        "loanreport.html",
        reports=reports
    )
# =========================================================
# DELETE LOAN - CUSTOMER
# =========================================================
@loan.route(
    "/deleteloan/<int:id>"
)
def deleteloan(id):
    if "customer_id" not in session:
        return redirect(
            url_for("customer.dashboard")
        )
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        DELETE FROM loan_application
        WHERE loan_id=%s
        AND customer_id=%s
        AND loan_status='Pending'
        """,
        (
            id,
            session["customer_id"]
        )
    )
    conn.commit()
    cursor.close()
    conn.close()
    flash(
        "Loan Deleted Successfully."
    )
    return redirect(
        url_for("loan.loanstatus")
    )
# =========================================================
# CUSTOMER LOAN DASHBOARD
# =========================================================
@loan.route("/loandashboard")
def loandashboard():
    if "customer_id" not in session:
        return redirect(
            url_for("customer.dashboard")
        )
    conn = get_db_connection()
    cursor = conn.cursor(
        dictionary=True
    )

    # -----------------------------------------------------
    # TOTAL
    # -----------------------------------------------------
    cursor.execute(
        """
        SELECT COUNT(*) AS total
        FROM loan_application
        WHERE customer_id=%s
        """,
        (
            session["customer_id"],
        )
    )
    total = cursor.fetchone()["total"]
    # -----------------------------------------------------
    # APPROVED
    # -----------------------------------------------------
    cursor.execute(
        """
        SELECT COUNT(*) AS approved
        FROM loan_application
        WHERE customer_id=%s
        AND loan_status='Approved'
        """,
        (
            session["customer_id"],
        )
    )
    approved = cursor.fetchone()["approved"]

    # -----------------------------------------------------
    # PENDING
    # -----------------------------------------------------
    cursor.execute(
        """
        SELECT COUNT(*) AS pending
        FROM loan_application
        WHERE customer_id=%s
        AND loan_status='Pending'
        """,
        (
            session["customer_id"],
        )
    )
    pending = cursor.fetchone()["pending"]
    # -----------------------------------------------------
    # REJECTED
    # -----------------------------------------------------
    cursor.execute(
        """
        SELECT COUNT(*) AS rejected
        FROM loan_application
        WHERE customer_id=%s
        AND loan_status='Rejected'
        """,
        (
            session["customer_id"],
        )
    )
    rejected = cursor.fetchone()["rejected"]
    cursor.close()
    conn.close()
    return render_template(
        "loandashboard.html",
        total=total,
        approved=approved,
        pending=pending,
        rejected=rejected
    )

# =========================================================
# LOAN LOGOUT
# =========================================================
@loan.route("/logout")
def logout():
    session.clear()
    flash(
        "Logged Out Successfully."
    )
    return redirect(
        url_for("customer.home")
    )