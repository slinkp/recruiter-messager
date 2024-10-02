import base64
import os

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

HERE = os.path.dirname(os.path.abspath(__file__))
AUTH_DIR = os.path.join(HERE, "secrets")
CREDENTIALS_FILE = os.path.join(AUTH_DIR, "credentials.json")
TOKEN_FILE = os.path.join(AUTH_DIR, "token.json")


class GmailSearcher:

    SCOPES = (
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.compose",
        "https://www.googleapis.com/auth/gmail.modify",
    )

    def __init__(self):
        self.creds = None
        self.service = None

    def authenticate(self):
        if os.path.exists(TOKEN_FILE):
            self.creds = Credentials.from_authorized_user_file(TOKEN_FILE, self.SCOPES)
        if not (self.creds and self.creds.valid):
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    CREDENTIALS_FILE, self.SCOPES
                )
                self.creds = flow.run_local_server(port=0)
            with open(TOKEN_FILE, "w") as token:
                token.write(self.creds.to_json())
        self.service = build("gmail", "v1", credentials=self.creds)

    def search_messages(self, query):
        results = self.service.users().messages().list(userId="me", q=query).execute()
        messages = results.get("messages", [])
        return messages

    def get_message_details(self, msg_id):
        message = self.service.users().messages().get(userId="me", id=msg_id).execute()
        return message

    def search_and_get_details(self, query):
        messages = self.search_messages(query)
        detailed_messages = []
        for msg in messages:
            detailed_messages.append(self.get_message_details(msg["id"]))
        return detailed_messages

    def extract_message_content(self, message):
        if "payload" not in message:
            return ""
        if "body" in message["payload"]:
            return base64.urlsafe_b64decode(message["payload"]["body"]["data"]).decode(
                "utf-8"
            )
        elif "parts" in message["payload"]:
            for part in message["payload"]["parts"]:
                if part["mimeType"] == "text/plain":
                    return base64.urlsafe_b64decode(part["body"]["data"]).decode(
                        "utf-8"
                    )
        return ""


if __name__ == "__main__":
    searcher = GmailSearcher()
    searcher.authenticate()
    results = searcher.search_and_get_details("label:jobs-2024/recruiter-pings")
    for msg in results:
        print(f"Subject: {msg['payload']['headers'][0]['value']}")
        # print(f"Content: {searcher.extract_message_content(msg)}")
        print("---")
