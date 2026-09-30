import pandas as pd

from sklearn.model_selection import train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score


# =========================================================
# TRAINING DATASET
# =========================================================

data = {
    "credit_score": [
        780, 760, 740, 720, 700,
        680, 660, 640, 620, 590,
        800, 770, 730, 710, 690,
        650, 630, 610, 580, 560,
        790, 750, 725, 705, 675,
        655, 635, 600, 570, 550
    ],

    "monthly_income": [
        80000, 70000, 60000, 55000, 50000,
        45000, 40000, 35000, 30000, 25000,
        90000, 75000, 65000, 60000, 48000,
        42000, 38000, 32000, 28000, 22000,
        85000, 72000, 58000, 52000, 44000,
        39000, 34000, 30000, 26000, 20000
    ],

    "loan_amount": [
        800000, 700000, 600000, 500000, 400000,
        500000, 450000, 400000, 300000, 500000,
        900000, 750000, 600000, 500000, 450000,
        400000, 350000, 300000, 400000, 300000,
        800000, 650000, 550000, 450000, 400000,
        350000, 300000, 250000, 300000, 250000
    ],

    "employment_type": [
        "Government", "Salaried", "Salaried", "Government", "Salaried",
        "Business", "Salaried", "Self Employed", "Salaried", "Daily Wages",
        "Government", "Salaried", "Business", "Government", "Salaried",
        "Self Employed", "Salaried", "Daily Wages", "Salaried", "Daily Wages",
        "Government", "Salaried", "Business", "Salaried", "Government",
        "Self Employed", "Salaried", "Daily Wages", "Salaried", "Daily Wages"
    ],

    "loan_term": [
        60, 60, 48, 48, 36,
        60, 48, 48, 36, 36,
        60, 60, 48, 48, 36,
        60, 48, 36, 36, 24,
        60, 60, 48, 48, 36,
        48, 36, 36, 24, 24
    ],

    "loan_type": [
        "Home Loan", "Home Loan", "Vehicle Loan", "Personal Loan", "Education Loan",
        "Business Loan", "Vehicle Loan", "Personal Loan", "Education Loan", "Personal Loan",
        "Home Loan", "Home Loan", "Business Loan", "Vehicle Loan", "Personal Loan",
        "Business Loan", "Vehicle Loan", "Personal Loan", "Education Loan", "Personal Loan",
        "Home Loan", "Home Loan", "Vehicle Loan", "Personal Loan", "Education Loan",
        "Business Loan", "Vehicle Loan", "Personal Loan", "Education Loan", "Personal Loan"
    ],

    "approved": [
        1, 1, 1, 1, 1,
        1, 1, 1, 1, 0,
        1, 1, 1, 1, 1,
        1, 0, 0, 0, 0,
        1, 1, 1, 1, 1,
        0, 0, 0, 0, 0
    ]
}


df = pd.DataFrame(data)


# =========================================================
# FEATURES AND TARGET
# =========================================================

X = df[
    [
        "credit_score",
        "monthly_income",
        "loan_amount",
        "employment_type",
        "loan_term",
        "loan_type"
    ]
]

y = df["approved"]


# =========================================================
# COLUMN DEFINITIONS
# =========================================================

categorical_columns = [
    "employment_type",
    "loan_type"
]

numeric_columns = [
    "credit_score",
    "monthly_income",
    "loan_amount",
    "loan_term"
]


# =========================================================
# PREPROCESSING
# =========================================================
#
# StandardScaler is important here because:
#
# credit_score       -> around 500 - 800
# monthly_income     -> around 20,000 - 90,000
# loan_amount        -> around 250,000 - 900,000
# loan_term          -> around 24 - 60
#
# Without scaling, loan_amount and income can dominate
# the Logistic Regression model.
#
# =========================================================

preprocessor = ColumnTransformer(
    transformers=[
        (
            "categorical",
            OneHotEncoder(
                handle_unknown="ignore"
            ),
            categorical_columns
        ),

        (
            "numeric",
            StandardScaler(),
            numeric_columns
        )
    ]
)


# =========================================================
# MACHINE LEARNING MODEL
# =========================================================

model = Pipeline(
    steps=[
        (
            "preprocessor",
            preprocessor
        ),

        (
            "classifier",
            LogisticRegression(
                max_iter=2000,
                class_weight="balanced",
                C=1.0,
                random_state=42
            )
        )
    ]
)


# =========================================================
# TRAIN / TEST SPLIT
# =========================================================

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.20,
    random_state=42,
    stratify=y
)


# =========================================================
# TRAIN MODEL
# =========================================================

model.fit(
    X_train,
    y_train
)


# =========================================================
# MODEL ACCURACY
# =========================================================

y_pred = model.predict(
    X_test
)

accuracy = accuracy_score(
    y_test,
    y_pred
)

MODEL_ACCURACY = round(
    accuracy * 100,
    2
)

print(
    "========================================"
)

print(
    "Loan Prediction Model Trained Successfully"
)

print(
    "Model Accuracy:",
    MODEL_ACCURACY,
    "%"
)

print(
    "========================================"
)


# =========================================================
# LOAN PREDICTION FUNCTION
# =========================================================

def predict_loan(
    credit_score,
    monthly_income,
    loan_amount,
    employment_type,
    loan_term,
    loan_type
):

    try:

        # -----------------------------------------
        # Convert numeric values safely
        # -----------------------------------------

        credit_score = float(
            credit_score
        )

        monthly_income = float(
            monthly_income
        )

        loan_amount = float(
            loan_amount
        )

        loan_term = float(
            loan_term
        )


        # -----------------------------------------
        # Create input DataFrame
        # -----------------------------------------

        input_data = pd.DataFrame(
            [
                {
                    "credit_score": credit_score,
                    "monthly_income": monthly_income,
                    "loan_amount": loan_amount,
                    "employment_type": str(
                        employment_type
                    ),
                    "loan_term": loan_term,
                    "loan_type": str(
                        loan_type
                    )
                }
            ]
        )


        # -----------------------------------------
        # Prediction
        # -----------------------------------------

        prediction = model.predict(
            input_data
        )[0]


        # -----------------------------------------
        # Probability
        # -----------------------------------------

        probabilities = model.predict_proba(
            input_data
        )[0]


        # Find the probability belonging
        # specifically to class 1 (Approved)

        classes = model.named_steps[
            "classifier"
        ].classes_

        if 1 in classes:

            approved_index = list(
                classes
            ).index(1)

            approval_probability = (
                probabilities[
                    approved_index
                ]
            )

        else:

            approval_probability = 0.0


        # -----------------------------------------
        # Result
        # -----------------------------------------

        if prediction == 1:

            result = "Approved"

        else:

            result = "Rejected"


        # -----------------------------------------
        # Return result
        # -----------------------------------------

        return (
            result,
            round(
                approval_probability * 100,
                2
            )
        )


    except Exception as e:

        print(
            "Loan Prediction Error:",
            e
        )

        # Do NOT silently create a wrong
        # prediction when there is an error.

        raise


# =========================================================
# TEST PREDICTIONS
# =========================================================
#
# These are only for checking the model when
# loan_model.py is executed directly.
#
# They will NOT affect your Flask application.
#
# =========================================================

if __name__ == "__main__":

    print()
    print(
        "========== TEST PREDICTIONS =========="
    )


    # -----------------------------------------
    # Test 1 - Strong applicant
    # -----------------------------------------

    result1, probability1 = predict_loan(
        780,
        80000,
        500000,
        "Government",
        60,
        "Home Loan"
    )

    print(
        "Test 1:",
        result1,
        "| Approval Probability:",
        probability1,
        "%"
    )


    # -----------------------------------------
    # Test 2 - Medium applicant
    # -----------------------------------------

    result2, probability2 = predict_loan(
        680,
        45000,
        400000,
        "Salaried",
        48,
        "Vehicle Loan"
    )

    print(
        "Test 2:",
        result2,
        "| Approval Probability:",
        probability2,
        "%"
    )


    # -----------------------------------------
    # Test 3 - Weak applicant
    # -----------------------------------------

    result3, probability3 = predict_loan(
        550,
        20000,
        500000,
        "Daily Wages",
        24,
        "Personal Loan"
    )

    print(
        "Test 3:",
        result3,
        "| Approval Probability:",
        probability3,
        "%"
    )

    print(
        "======================================="
    )