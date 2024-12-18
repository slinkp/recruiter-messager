from langchain_community.document_loaders.recursive_url_loader import RecursiveUrlLoader
from bs4 import BeautifulSoup
import io
import re


def bs4_extractor(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    text = re.sub(r"\n\n+", "\n\n", soup.text).strip()
    return text


url = "https://docs.llamaindex.ai/en/stable/"
loader = RecursiveUrlLoader(url=url, max_depth=2, extractor=bs4_extractor)

LIMIT = 4

with io.open("url.txt", "w", encoding="utf-8") as f1:
    for i, doc in enumerate(loader.lazy_load()):
        url = doc.metadata["source"]
        print(f"{i} Got {url}: {doc.page_content[:100]}")
        f1.write(f"{url}\n")
        if i == LIMIT - 1:
            break
