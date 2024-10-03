import os
from typing import List, Tuple


from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter


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