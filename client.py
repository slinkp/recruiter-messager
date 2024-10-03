import base64
import os
import re
from typing import List, Tuple

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter

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
        return text.strip()

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
        linkedin_garbage_lines = (
            "This email was intended for",
            "Get the new LinkedIn",
            "Also available on mobile",
        )
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

    def get_recruiter_messages(
        self, query: str, max_results: int = 10
    ) -> List[Tuple[str, str, str]]:
        results = (
            self.service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )
        messages = results.get("messages", [])
        processed_messages = []

        for msg in messages:
            full_msg = self.get_message_details(msg["id"])
            subject = self.get_subject(full_msg)
            content = self.extract_message_content(full_msg)
            my_reply, recruiter_message = self.split_message(content)
            processed_messages.append((subject, recruiter_message, my_reply))

        return processed_messages


class RecruitmentRAG:
    def __init__(self, messages: List[Tuple[str, str, str]]):
        self.messages = messages
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, chunk_overlap=200
        )
        self.embeddings = OpenAIEmbeddings()
        self.vectorstore = None
        self.retriever = None
        self.chain = None

    def prepare_data(self):
        documents = []
        for subject, recruiter_message, my_reply in self.messages:
            documents.append(
                f"Subject: {subject}\nRecruiter: {recruiter_message}\nMy Reply: {my_reply}"
            )

        split_docs = self.text_splitter.create_documents(documents)
        self.vectorstore = Chroma.from_documents(
            documents=split_docs, embedding=self.embeddings
        )
        self.retriever = self.vectorstore.as_retriever(search_kwargs={"k": 3})

    def setup_chain(self):
        llm = ChatOpenAI(temperature=0.2)

        template = """You are an AI assistant helping to generate replies to recruiter messages
        based on previous interactions. 
        Use the following pieces of context to generate a reply to the recruiter message. 
        The reply should be professional, courteous, and in a similar style to the previous replies.
        If the recruiter message provides specific information that is an especially good match for 
        most orall the criteria that previous context has indicated the candidate wants,
        then the tone should be more excited.
        Otherwise, be specific about criteria that are not met, including dollar amounts for compensation.

        Context: {context}

        Recruiter Message: {question}

        Generated Reply:"""

        prompt = ChatPromptTemplate.from_template(template)

        self.chain = (
            {"context": self.retriever, "question": RunnablePassthrough()}
            | prompt
            | llm
            | StrOutputParser()
        )

    def generate_reply(self, new_recruiter_message: str) -> str:
        return self.chain.invoke(new_recruiter_message)


if __name__ == "__main__":
    searcher = GmailSearcher()
    searcher.authenticate()

    # Fetch recruiter messages and your replies
    query = "label:jobs-2024/recruiter-pings from:me"
    processed_messages = searcher.get_recruiter_messages(query)

    # Set up the RAG pipeline
    rag = RecruitmentRAG(processed_messages)
    rag.prepare_data()
    rag.setup_chain()

    # Example usage
    demo_messages = (
        "Hi there! I came across your profile and was impressed by your experience. We have an exciting opportunity for a Senior Software Engineer position. Would you be interested in learning more?",
        "Hello, would you be interested in a contract position? It pays $75 per hour.",
        "Hi are you available for a call tomorrow? I have a great opportunity for a junior full stack engineer.",
        "Hey Paul! Come work for me in San Francisco!",
        "I have a permanent role open for a senior staff python backend developer who wants to learn AI. It pays $999k. The company is well established, public, and is in NYC",
    )
    import textwrap

    for new_recruiter_message in demo_messages:
        generated_reply = rag.generate_reply(new_recruiter_message)
        generated_reply = textwrap.fill(generated_reply, width=70)
        new_recruiter_message = textwrap.fill(new_recruiter_message, width=70)
        print("-" * 80 + "\n")
        print(f"New Recruiter Message (demo):\n {new_recruiter_message}\n")
        print(f"Generated Reply:\n {generated_reply}\n\n")
