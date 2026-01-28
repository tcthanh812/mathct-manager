import streamlit as st
import json
import gspread
from gspread.exceptions import WorksheetNotFound, APIError
from google.oauth2.service_account import Credentials
# -----------------------------
# Google Sheets client (safe to cache)
# -----------------------------
@st.cache_resource
def get_gsheets_client():
    creds_dict = st.secrets["GOOGLE_SHEETS_CREDENTIALS"]
    if isinstance(creds_dict, str):
        creds_dict = json.loads(creds_dict)

    credentials = Credentials.from_service_account_info(
        creds_dict,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    return gspread.authorize(credentials)

@st.cache_resource
def get_spreadsheet():
    client = get_gsheets_client()
    sheet_id = st.secrets["GOOGLE_SHEET_ID"]
    return client.open_by_key(sheet_id)