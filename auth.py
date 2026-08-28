import os
import hashlib
import hmac

import streamlit as st
from dotenv import load_dotenv

load_dotenv()


# ============================================================
# PASSWORD HASH
# ============================================================

def hash_password(password: str) -> str:
    return hashlib.sha256(
        password.encode("utf-8")
    ).hexdigest()


# ============================================================
# USER CONFIG
# ============================================================

USERS = {
    os.getenv("ADMIN_USERNAME", "admin"): {
        "password": os.getenv(
            "ADMIN_PASSWORD",
            "admin123"
        ),
        "role": "admin"
    },

    os.getenv("OPERATOR_USERNAME", "operator"): {
        "password": os.getenv(
            "OPERATOR_PASSWORD",
            "operator123"
        ),
        "role": "operator"
    },

    os.getenv("VIEWER_USERNAME", "viewer"): {
        "password": os.getenv(
            "VIEWER_PASSWORD",
            "viewer123"
        ),
        "role": "viewer"
    }
}


# ============================================================
# SESSION
# ============================================================

def init_session():

    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if "username" not in st.session_state:
        st.session_state.username = None

    if "role" not in st.session_state:
        st.session_state.role = None


# ============================================================
# LOGIN
# ============================================================

def login():

    init_session()

    if st.session_state.authenticated:
        return True

    st.markdown(
        """
        <style>

        .login-box {
            max-width: 450px;
            margin: 80px auto;
            padding: 30px;
            border-radius: 15px;
            border: 1px solid #ddd;
            background-color: white;
        }

        </style>
        """,
        unsafe_allow_html=True
    )

    st.markdown(
        "<h1 style='text-align:center;'>🛡️</h1>",
        unsafe_allow_html=True
    )

    st.title(
        "Login Dashboard Patroli Siber"
    )

    st.caption(
        "Silakan masuk menggunakan akun yang telah diberikan."
    )

    username = st.text_input(
        "Username",
        key="login_username"
    )

    password = st.text_input(
        "Password",
        type="password",
        key="login_password"
    )

    if st.button(
        "🔐 Masuk",
        use_container_width=True
    ):

        user = USERS.get(username)

        if user:

            password_valid = hmac.compare_digest(
                str(user["password"]),
                str(password)
            )

            if password_valid:

                st.session_state.authenticated = True
                st.session_state.username = username
                st.session_state.role = user["role"]

                st.success(
                    "Login berhasil."
                )

                st.rerun()

        st.error(
            "Username atau password salah."
        )

    return False


# ============================================================
# LOGOUT
# ============================================================

def logout():

    st.session_state.authenticated = False
    st.session_state.username = None
    st.session_state.role = None

    st.rerun()


# ============================================================
# ROLE
# ============================================================

def get_current_user():

    init_session()

    return {
        "username": st.session_state.username,
        "role": st.session_state.role
    }


def is_admin():

    return (
        st.session_state.get("role")
        == "admin"
    )


def is_operator():

    return (
        st.session_state.get("role")
        in [
            "admin",
            "operator"
        ]
    )


def is_viewer():

    return (
        st.session_state.get("role")
        == "viewer"
    )
