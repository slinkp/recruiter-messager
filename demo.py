import textwrap
from client import GmailSearcher
from rag import RecruitmentRAG


def main():
    print("Fetching messages from mail...")
    searcher = GmailSearcher()
    searcher.authenticate()

    # Fetch recruiter messages and your replies
    query = "label:jobs-2024/recruiter-pings from:me"
    processed_messages = searcher.get_recruiter_messages(query, max_results=100)
    print(f"Got messages from mail: {len(processed_messages)}")

    # Set up the RAG pipeline
    rag = RecruitmentRAG(processed_messages)
    rag.prepare_data()
    rag.setup_chain()
    print(f"RAG setup complete")

    # Example usage
    demo_messages = (
        "Hi there! I came across your profile and was impressed by your experience. We have an exciting opportunity for a Senior Software Engineer position. Would you be interested in learning more?",
        "Hello, would you be interested in a contract position? It pays $75 per hour.",
        "Hi are you available for a call tomorrow? I have a great opportunity for a junior full stack engineer.",
        "Hey Paul! Come work for me in San Francisco!",
        "I have a permanent role open for a senior staff python backend developer who wants to learn AI. It pays $999k. The company is well established, public, and is in NYC",
    )

    for new_recruiter_message in demo_messages:
        generated_reply = rag.generate_reply(new_recruiter_message)
        generated_reply = textwrap.fill(generated_reply, width=70)
        new_recruiter_message = textwrap.fill(new_recruiter_message, width=70)
        print("-" * 80 + "\n")
        print(f"New Recruiter Message (demo):\n {new_recruiter_message}\n")
        print(f"Generated Reply:\n {generated_reply}\n\n")


if __name__ == "__main__":
    main()
