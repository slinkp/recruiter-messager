import base64
import os
import re
from typing import List, Tuple

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.exceptions import RefreshError

HERE = os.path.dirname(os.path.abspath(__file__))
AUTH_DIR = os.path.join(HERE, "secrets")
CREDENTIALS_FILE = os.path.join(AUTH_DIR, "credentials.json")
TOKEN_FILE = os.path.join(AUTH_DIR, "token.json")


class GmailRepliesSearcher:
    """
    Searches for user's previous replies to recruiter emails.

    Intended to be used to feed into a RAG system to help it understand the
    user's communication style.
    """

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
                try:
                    self.creds.refresh(Request())
                except RefreshError:
                    # Token is invalid, so we need to re-authenticate
                    self.creds = None
            if not self.creds or not self.creds.valid:
                flow = InstalledAppFlow.from_client_secrets_file(
                    CREDENTIALS_FILE, self.SCOPES
                )
                self.creds = flow.run_local_server(port=0)
            with open(TOKEN_FILE, "w") as token:
                token.write(self.creds.to_json())
        self.service = build("gmail", "v1", credentials=self.creds)

    def search_messages(self, query, max_results: int = 10) -> list:
        results = (
            self.service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )
        messages = results.get("messages", [])
        return messages

    def get_message_details(self, msg_id):
        message = self.service.users().messages().get(userId="me", id=msg_id).execute()
        return message

    def search_and_get_details(self, query, max_results: int = 10):
        messages = self.search_messages(query, max_results)
        detailed_messages = [self.get_message_details(msg["id"]) for msg in messages]
        return detailed_messages

    def extract_message_content(self, message):
        try:
            # Attempt to access the 'data' key
            data = message["payload"]["body"]["data"]
            return base64.urlsafe_b64decode(data).decode()
        except KeyError:
            # If 'data' is not found, check for 'parts'
            parts = message["payload"].get("parts", [])
            if parts:
                for part in parts:
                    if part["mimeType"] == "text/plain":
                        data = part["body"]["data"]
                        return base64.urlsafe_b64decode(data).decode()

            # If no suitable content is found, return an error message
            return "Unable to extract message content"

    def clean_reply(self, text):
        text = text.strip()
        if len(text) < 30:
            # Heuristic for stuff like 'replied on linkedin'
            return ""
        return text

    def _is_garbage_line(self, line):
        linkedin_garbage_lines = (
            "This email was intended for",
            "Get the new LinkedIn",
            "Also available on mobile",
            "*Tip:* You can respond to ",
        )
        for garbage in linkedin_garbage_lines:
            if line.startswith(garbage):
                return True
        return False

    def clean_quoted_text(self, text):
        lines = text.splitlines()
        cleaned_lines = []
        for line in lines:
            line = line.lstrip("> ")
            line = re.sub(r"<\S+>", "", line)
            line = re.sub(r"\[image:.*?\]", "", line, flags=re.MULTILINE)
            line = line.strip()
            if self._is_garbage_line(line):
                break
            if line:
                cleaned_lines.append(line)
        return "\n".join(cleaned_lines)

    def split_message(self, content):
        pattern = r"\nOn .+?(?:\d{1,2}:\d{2}(?: [AP]M)?|\d{4}).*?(?:\S+@\S+|<\S+@\S+>)\s+wrote:"
        match = re.split(pattern, content, flags=re.DOTALL | re.IGNORECASE)
        if len(match) > 1:
            reply_text = self.clean_reply(match[0])
            quoted_text = self.clean_quoted_text(match[-1])
        else:
            reply_text = self.clean_reply(content)
            quoted_text = ""
        return reply_text, quoted_text

    def get_subject(self, message):
        for header in message["payload"]["headers"]:
            if header["name"].lower() == "subject":
                return header["value"]
        return "No Subject"

    def get_recruiter_replies(
        self, query: str, max_results: int = 10
    ) -> List[Tuple[str, str, str]]:
        results = self.search_and_get_details(query, max_results)
        print(f"Got {len(results)} messages")
        processed_messages = []

        for full_msg in results:
            subject = self.get_subject(full_msg)
            content = self.extract_message_content(full_msg)
            date = full_msg["internalDate"]
            my_reply, recruiter_message = self.split_message(content)
            if my_reply and recruiter_message:
                processed_messages.append(
                    (date, (subject, recruiter_message, my_reply))
                )
            else:
                print(f"Skipping message with no useful content: {subject}")

        processed_messages.sort(reverse=True)
        return [msg for _, msg in processed_messages]


if __name__ == "__main__":
    searcher = GmailRepliesSearcher()
    searcher.authenticate()
    query = "label:jobs-2024/recruiter-pings from:me"
    processed_messages = searcher.get_recruiter_replies(query, max_results=10)
    processed_messages = processed_messages[:3]
    import textwrap

    term_width = 75
    max_lines = 4
    for subject, recruiter_message, my_reply in processed_messages:
        subject = textwrap.fill(subject, width=term_width)
        recruiter_message = textwrap.fill(
            recruiter_message, width=term_width, max_lines=max_lines
        )
        my_reply = textwrap.fill(my_reply, width=term_width, max_lines=max_lines)
        print(f"Subject: {subject}")
        print(f"\nRecruiter Message:\n{recruiter_message}")
        print(f"\nMy Reply:\n{my_reply}")
        print()
        print("-" * term_width)
        print()
