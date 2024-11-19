import os.path
import textwrap
import json
import logging
import email_client
from rag import RecruitmentRAG

HERE = os.path.dirname(os.path.abspath(__file__))

def load_messages(use_cache: bool = True):

    cachefile = os.path.join(HERE, "processed_messages.json")
    processed_messages = []
    if use_cache:
        try:
            with open(cachefile, "r") as f:
                processed_messages = json.load(f)
                print(f"Loaded {len(processed_messages)} messages from cache")
        except FileNotFoundError:
            print("No cache found, rebuilding...")
    if not processed_messages:
        print("Fetching messages from mail...")
        searcher = email_client.GmailRepliesSearcher()
        searcher.authenticate()
        processed_messages = searcher.get_my_replies_to_recruiters(
            query=email_client.RECRUITER_REPLIES_QUERY, max_results=300
        )
        print(f"Got messages from mail: {len(processed_messages)}")
        with open(cachefile, "w") as f:
            json.dump(processed_messages, f, indent=2)

    return processed_messages


def main(model: str, limit: int, use_cache: bool = True, loglevel: int = logging.INFO):
    processed_messages = load_messages(use_cache)

    # Set up the RAG pipeline
    rag = RecruitmentRAG(processed_messages, loglevel=loglevel)
    rag.prepare_data(clear_existing=not use_cache)
    rag.setup_chain(llm_type=model)
    print(f"RAG setup complete")

    # Example usage
    demo_messages = [
        "Hi there! I came across your profile and was impressed by your experience. We have an exciting opportunity for a Senior Software Engineer position. Would you be interested in learning more?",
        "Hello, would you be interested in a contract position? It pays $35 per hour.",
        "Hi are you available for a call tomorrow? I have a great opportunity for a junior full stack engineer.",
        "Hey Paul! Come work for me in San Francisco! Regards, Jobby McJobface",
        "I have a permanent role open for a senior staff python backend developer who wants to learn AI. It pays $999k. The company is well established, public, and is in NYC",
    ]
    demo_messages.reverse()
    demo_messages = demo_messages[:limit]

    for new_recruiter_message in demo_messages:
        generated_reply = rag.generate_reply(new_recruiter_message)
        generated_reply = textwrap.fill(generated_reply, width=70)
        new_recruiter_message = textwrap.fill(new_recruiter_message, width=70)
        print("-" * 80 + "\n")
        print(f"New Recruiter Message (demo):\n {new_recruiter_message}\n")
        print(f"Generated Reply:\n {generated_reply}\n\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model", action="store", choices=["openai", "claude"], default="openai"
    )
    parser.add_argument(
        "--limit",
        action="store",
        type=int,
        default=10,
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        default=False,
        help="Do not use cached messages from Gmail",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        help="Print verbose logging",
    )
    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    main(
        args.model,
        limit=args.limit,
        use_cache=not args.no_cache,
        loglevel=logging.DEBUG,
    )
