import os
from typing import List, Tuple


from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_anthropic import ChatAnthropic
from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter


TEMPLATE = """You are an AI assistant helping to generate replies to recruiter messages
based on previous interactions.
Use the following pieces of context to generate a reply to the recruiter message.
The reply should be professional, courteous, and in a similar style to the previous replies.
If the recruiter message provides specific information that is an especially good match for
most or all the criteria that previous context has indicated the candidate wants,
then the tone should be more excited.
Otherwise, be specific about criteria that are not met, including dollar amounts for
compensation.
To clarify the criteria: Decline opportunities with compensation that is too low, but do
not decline if compensation is higher than the minimum from previous context.
Higher is better and no amount is too high!

Context: {context}

Recruiter Message: {question}

Generated Reply:"""


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

    def setup_chain(self, llm_type: str):
        if self.retriever is None:
            raise ValueError("Data not prepared. Call prepare_data() first.")

        if llm_type.lower() == "openai":
            llm = ChatOpenAI(temperature=0.2)
        elif llm_type.lower() == "claude":
            llm = ChatAnthropic(model="claude-3-5-sonnet-20240620", temperature=0.2)
        else:
            raise ValueError("Invalid llm_type. Choose 'openai' or 'claude'.")

        prompt = ChatPromptTemplate.from_template(TEMPLATE)

        self.chain = (
            {"context": self.retriever, "question": RunnablePassthrough()}
            | prompt
            | llm
            | StrOutputParser()
        )

    def generate_reply(self, new_recruiter_message: str) -> str:
        if self.chain is None:
            raise ValueError("Chain not set up. Call setup_chain() first.")
        return self.chain.invoke(new_recruiter_message)
