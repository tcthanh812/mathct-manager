# Google Sheets Setup Guide

This app has been migrated from Supabase to Google Sheets. Follow these steps to set up the Google Sheets integration:

## Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable the following APIs:
   - Google Sheets API
   - Google Drive API

## Step 2: Create a Service Account

1. In Google Cloud Console, go to **Credentials**
2. Click **Create Credentials** → **Service Account**
3. Fill in the service account details and click **Create**
4. Click on the created service account
5. Go to the **Keys** tab
6. Click **Add Key** → **Create new key**
7. Choose **JSON** and click **Create**
8. A JSON file will be downloaded - keep this safe

## Step 3: Create a Google Sheet

1. Go to [Google Sheets](https://sheets.google.com/)
2. Create a new spreadsheet
3. Name it something like "Teaching Schedule"
4. Get the **Spreadsheet ID** from the URL:
   - URL format: `https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit`

## Step 4: Share the Spreadsheet

1. Click the **Share** button in your spreadsheet
2. Add the service account email (from the JSON file: `client_email`)
3. Give it **Editor** access

## Step 5: Create Sheet Tabs

In your spreadsheet, create exactly 3 sheets with these names:
- `classes`
- `class_rules`
- `schedule_overrides`

### Sheet: `classes`
Add header row:
```
id, class_name, rate, active, note, updated_at
```

### Sheet: `class_rules`
Add header row:
```
id, class_id, weekday, duration_hours, start_date, end_date, note, updated_at
```

### Sheet: `schedule_overrides`
Add header row:
```
class_name, year, month, data, updated_at
```

## Step 6: Configure Streamlit Secrets

Create or update `.streamlit/secrets.toml` with:

```toml
APP_PASSWORD = "your_password_here"

GOOGLE_SHEET_ID = "your_spreadsheet_id_here"

GOOGLE_SHEETS_CREDENTIALS = {
    "type": "service_account",
    "project_id": "your_project_id",
    "private_key_id": "your_private_key_id",
    "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
    "client_email": "your_service_account_email@project.iam.gserviceaccount.com",
    "client_id": "your_client_id",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/..."
}
```

You can copy the JSON structure directly from the service account JSON file you downloaded.

## Step 7: Install Dependencies

```bash
pip install -r requirements.txt
```

## Step 8: Run the App

```bash
streamlit run streamlit_app.py
```

## Notes

- The spreadsheet is **private** and only accessible to your service account
- The app has full **read and edit** access to the Google Sheet
- All operations are logged with `updated_at` timestamps
- The data structure matches your previous Supabase setup for seamless migration
