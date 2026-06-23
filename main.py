import os
import os.path
import sqlite3
import requests

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


class EmailDecision(BaseModel):
    category: str
    priority: str
    summary: str
    action_required: str
    deadline: str
    decision: str


def init_db():
    conn = sqlite3.connect("school_emails.db")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS email_tasks (
            email_id TEXT PRIMARY KEY,
            subject TEXT,
            summary TEXT,
            priority TEXT,
            decision TEXT,
            status TEXT,
            pushover_receipt TEXT
        )
    """)

    conn.commit()
    conn.close()


def is_task_exists(email_id):
    conn = sqlite3.connect("school_emails.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT email_id
        FROM email_tasks
        WHERE email_id = ?
    """, (email_id,))

    result = cursor.fetchone()
    conn.close()

    return result is not None


def save_email_task(email, decision, receipt=None):
    conn = sqlite3.connect("school_emails.db")
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO email_tasks
        (email_id, subject, summary, priority, decision, status, pushover_receipt)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        email["id"],
        email["subject"],
        decision.summary,
        decision.priority,
        decision.decision,
        "pending" if decision.decision == "notify" else "completed",
        receipt
    ))

    conn.commit()
    conn.close()


def get_pending_tasks():
    conn = sqlite3.connect("school_emails.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT email_id, subject, summary, priority, status, pushover_receipt
        FROM email_tasks
        WHERE status = 'pending'
    """)

    rows = cursor.fetchall()
    conn.close()

    return rows


def update_task_status(email_id, status):
    conn = sqlite3.connect("school_emails.db")
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE email_tasks
        SET status = ?
        WHERE email_id = ?
    """, (status, email_id))

    conn.commit()
    conn.close()


def show_tasks():
    conn = sqlite3.connect("school_emails.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT email_id, subject, priority, status, pushover_receipt
        FROM email_tasks
    """)

    rows = cursor.fetchall()

    for row in rows:
        print(row)

    conn.close()


def send_notification(message, emergency=False):
    data = {
        "token": os.getenv("PUSHOVER_API_TOKEN"),
        "user": os.getenv("PUSHOVER_USER_KEY"),
        "message": message,
        "title": "School Email Alert"
    }

    if emergency:
        data["priority"] = 2
        data["retry"] = 60
        data["expire"] = 3600

    response = requests.post(
        "https://api.pushover.net/1/messages.json",
        data=data
    )

    if response.status_code == 200:
        print("\n*** PUSHOVER NOTIFICATION SENT ***")
        return response.json()

    print("\n*** PUSHOVER NOTIFICATION FAILED ***")
    print(response.text)
    return None


def check_pushover_receipt(receipt):
    response = requests.get(
        f"https://api.pushover.net/1/receipts/{receipt}.json",
        params={"token": os.getenv("PUSHOVER_API_TOKEN")}
    )

    if response.status_code == 200:
        return response.json()

    print("\n*** FAILED TO CHECK PUSHOVER RECEIPT ***")
    print(response.text)
    return None


def sync_acknowledged_tasks():
    pending_tasks = get_pending_tasks()

    for task in pending_tasks:
        email_id, subject, summary, priority, status, receipt = task

        if not receipt:
            continue

        receipt_status = check_pushover_receipt(receipt)

        if receipt_status and receipt_status.get("acknowledged") == 1:
            update_task_status(email_id, "completed")
            print(f"Task acknowledged in Pushover and marked completed: {subject}")


def add_to_digest(message):
    print("\n*** ADDED TO DAILY DIGEST ***")
    print(message, "\n")


def ignore_email(message):
    print("\n*** EMAIL IGNORED ***")
    print(message, "\n")


def analyze_email(email):
    response = client.beta.chat.completions.parse(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": """
You are a school email triage agent.

Analyze the email and return a structured decision.

Categories:
- Action Required
- Event
- Deadline
- Newsletter
- FYI
- Ignore

Priority:
- High
- Medium
- Low

Decision:
- notify
- digest
- ignore
"""
            },
            {
                "role": "user",
                "content": str(email)
            }
        ],
        response_format=EmailDecision
    )

    return response.choices[0].message.parsed


def get_gmail_service():
    creds = None

    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json",
                SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open("token.json", "w") as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def get_header_value(headers, header_name, default=""):
    return next(
        (header["value"] for header in headers if header["name"] == header_name),
        default
    )


def main():
    init_db()
    service = get_gmail_service()

    results = service.users().messages().list(
        userId="me",
        labelIds=["INBOX"],
        maxResults=5
    ).execute()

    messages = results.get("messages", [])

    print(f"Found {len(messages)} emails")

    for message in messages:
        if is_task_exists(message["id"]):
            print("Skipping already processed email:", message["id"])
            continue

        msg = service.users().messages().get(
            userId="me",
            id=message["id"]
        ).execute()

        headers = msg["payload"]["headers"]

        subject = get_header_value(headers, "Subject", "(No Subject)")
        sender = get_header_value(headers, "From", "(Unknown Sender)")
        snippet = msg.get("snippet", "")

        email = {
            "id": message["id"],
            "sender": sender,
            "subject": subject,
            "body": snippet
        }

        print(email)

        decision = analyze_email(email)

        print(decision, "\n")
        print("Category:", decision.category)
        print("Priority:", decision.priority)
        print("Decision:", decision.decision)

        if decision.decision == "notify":
            pushover_response = send_notification(
                decision.summary,
                emergency=True
            )

            receipt = None
            if pushover_response:
                receipt = pushover_response.get("receipt")

            save_email_task(email, decision, receipt)

        elif decision.decision == "digest":
            add_to_digest(decision.summary)
            save_email_task(email, decision)

        else:
            ignore_email(decision.summary)
            save_email_task(email, decision)

    sync_acknowledged_tasks()

    print("\nEMAIL TASKS")
    show_tasks()

    print("\nPENDING TASKS")
    for task in get_pending_tasks():
        print(task)


if __name__ == "__main__":
    main()