from typing import Optional
from groq import Groq
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_hyperbrowser import HyperbrowserLoader
import dotenv, os, json, uvicorn, requests, datetime, re, markdown, time, io
from requests import TooManyRedirects
from sqlmodel import SQLModel, Field, create_engine, Session, select
from sqlalchemy.exc import NoResultFound, MultipleResultsFound
from bs4 import BeautifulSoup
import cohere
import pdfplumber

dotenv.load_dotenv()

MODE = "deployment"

assert MODE == "testing" or MODE == "deployment"

class SiteDataRequestManager:

    def __init__(self):
        self.current_url = None
        self.document = None
        self.requests_response = None
        self.error = False
        self.doctype = None

        self.request_headers = {
              "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
              "Accept": "text/html,application/xhtml+xml",
              "Accept-Language": "en-US,en;q=0.9",
              "Referer": "https://chatterhigh.com/"
          }

    def safe_get(self, url, **cookies):
        print("Calling Safe Get")

        try:
            response = requests.get(url=url, headers=self.request_headers, cookies=cookies, timeout=20)
            self.error = False
        except (requests.exceptions.ConnectTimeout, requests.exceptions.SSLError):
            self.current_url = ""
            self.error = True
            return

        self.current_url = response.url
        ctype = response.headers.get("Content-Type")

        data = bytearray()
        for chunk in response.iter_content(8192):
            data.extend(chunk)
            if len(data) > 5000000:
                print("Data too large!")
                self.error = True
                return

        print("ctype", ctype)
        if ctype.startswith("text/html"):
            self.requests_response = response
            self.document = response.text
            self.doctype = "html"
        elif ctype.startswith("application/pdf"):
            print("parsed as pdf")
            d = ""
            stream = io.BytesIO(response.content)
            with pdfplumber.open(stream) as pdf:
                for page in pdf.pages:
                    d += page.extract_text()

            self.requests_response = response
            self.document = d
            self.doctype = "pdf"
        else:
          raise ValueError("Incorrect Content Type")

    def get_final_url(self, url, session_token):
        print(self.current_url)
        if self.current_url != url:
            self.safe_get(url, _chatterhigh_session_1=session_token)

        if not self.error:
            return self.requests_response.url
        else:
            return None

    def get_site_content(self, url):
        if self.current_url != url:
            self.safe_get(url)
        if not self.error:
            return self.document
        else:
            return None

    def get_doctype(self):
        return self.doctype

def convert_to_html(mk):
    converted = markdown.markdown(mk, extensions=["tables"])
    converted = converted.replace("\n", "<br>")
    converted = converted.replace('"', "'")

    return converted

class Scraper:
    def __init__(self):
        self.api_key = os.environ["HYPERBROWSER_API_KEY"]

    def hyperbrowser_scrape(self, link):
        loader = HyperbrowserLoader(
            urls=link,
            api_key=self.api_key
        )

        r = loader.load()

        return r[0].page_content

    def scrape(self, link):

        raw_data = request_access.get_site_content(link)
        if raw_data is not None:
            if request_access.get_doctype() == "pdf":
                return raw_data
            else:
                soup = BeautifulSoup(raw_data, features="html.parser")

                if len(soup.text) > 2500:
                    print("Using requests scrape")
                    return re.sub(pattern=re.compile("\n+"), repl="\n", string=soup.text)
                else:
                    print("Falling back to Hyperbrowser")
                    return self.hyperbrowser_scrape(link)
        else:
            return self.hyperbrowser_scrape(link)



class AIAccess:

    def __init__(self):
        self.scraper = Scraper()
        self.ai_key = os.environ["GROQ_KEY"]
        self.text_gen_model = Groq(
            api_key=self.ai_key,
            default_headers={
                "Groq-Model-Version": "latest"
            }
        )
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=100
        )
        self.model = "openai/gpt-oss-20b"
        self.embedding_model = cohere.ClientV2()
        with open("prompts.json", "r") as p:
            self.json_file = json.load(p)

    def find_top_segment(self, query, document):
        segments = self.splitter.split_text(document)
        query_enhanced = self.text_gen_model.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
                {
                    'role': 'user',
                    'content': "Rewrite this query in the form of a question to enhance RAG (Retrieval Augmented"
                               "Generation) performance. \n ### Query: {query}".format(query=query)

                },
            ],
            include_reasoning=False
        ).choices[0].message.content
        for i in range(5):

            try:
                results = self.embedding_model.rerank(
                    model="rerank-v3.5",
                    query=query_enhanced,
                    documents=segments,
                    top_n=5
                )
                break
            except cohere.errors.TooManyRequestsError as e:
                time.sleep(5)
                print("Rate limit hit on cohere", e)

        else:
            print("429!")

        print("r", results)
        relevant_items = []
        for item in results.results:
            if item.relevance_score >= 0.9:
                relevant_items.append(segments[item.index])
                print(relevant_items)
        else:
            if len(relevant_items) == 0:
                first_item_index = results.results[0].index
                return segments[first_item_index]
            else:
                print("RI", relevant_items)
                return relevant_items

    def generate_prompt(self, question, choices, link, session_token):
        final_url = request_access.get_final_url(link, session_token)
        if final_url is not None:
            document = self.scraper.scrape(link=final_url)
            t = self.find_top_segment(query=question, document=document)
            prompt = self.json_file["answer_quiz"].format(question=question, choices=choices, excerpt=t, source=link)
            return [], prompt
        else:
            prompt = self.json_file["answer_quiz_error"].format(question=question, choices=choices)
            return [{"type":"browser_search"}], prompt

    def generate_summarizer_prompt(self, documents):
        combined_documents = ""
        for document in documents:
            try:
                combined_documents += document + " : "
                combined_documents += database_access.get_by_question(document).correct_answer
                combined_documents += "\n"
            except AttributeError:
                continue

        prompt = self.json_file["summarize"].format(data=documents)
        return prompt

    def get_html_id(self, text):
        pattern = re.compile("answer_id_[0-9]+")
        match = re.findall(pattern=pattern, string=text)
        if len(match) > 0:
            return match[0]
        else:
            return None

    def call_answer_question(self, question, choices: dict, link, session_token):
        reverse_choices = dict((choices[key], key) for key in choices.keys())
        for key in choices.keys():
            result = database_access.get_by_details(correct_answer=choices[key], question=question)
            if result is not None:
                try:
                    return reverse_choices[result.correct_answer]
                except KeyError:
                    continue


        begin = datetime.datetime.now()
        tools, prompt_generate_content = self.generate_prompt(question=question, choices=choices, link=link,
                                                session_token=session_token)
        messages = [
            {
                'role': 'user',
                'content': prompt_generate_content,

            },
        ]
        print("Prompt", messages)

        res = self.text_gen_model.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=messages,
            include_reasoning=False,
            tools=tools
        )

        print("Process completed with a time of", (datetime.datetime.now() - begin).total_seconds())
        print("Tokens used", res.usage.total_tokens)
        return self.get_html_id(res.choices[0].message.content)

    def call_summarizer(self, documents):
        begin = datetime.datetime.now()
        messages = [
            {
                'role': 'user',
                'content': self.generate_summarizer_prompt(
                    documents=documents
                ),

            }
        ]
        res = self.text_gen_model.chat.completions.create(
            model=self.model,
            temperature=0.5,
            messages=messages,
            include_reasoning=False
        )
        print("Process completed with a time of", (datetime.datetime.now() - begin).total_seconds())
        print("Tokens used", res.usage.total_tokens)
        return res.choices[0].message.content


class MCQModel(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    correct_answer: str
    question: str

class QuestionDatabaseControl:
    def __init__(self):

        self.DATABASE_URL = "postgresql://postgres.jpsimagftntgasqzuvnd:{password}@aws-1-ca-central-1.pooler.supabase.com:6543/postgres".format(password=os.environ["SUPABASE_KEY"])
        self.engine = create_engine(self.DATABASE_URL)
        SQLModel.metadata.create_all(self.engine)

    def add(self, correct_answer, question):
        with Session(self.engine) as session:
            try:
                item = session.exec(select(MCQModel).where(MCQModel.question == question)).one()
                if item.correct_answer == correct_answer:
                    print("Item already exists")
                else:
                    item.correct_answer = correct_answer
                    session.add(item)
                    session.commit()
            except NoResultFound:
                l = self.get_by_details(correct_answer, question)
                if l is None:
                    session.add(MCQModel(correct_answer=correct_answer, question=question))
                    session.commit()
            except MultipleResultsFound:
                print("Multiple results found for", correct_answer, question)

    def get_by_details(self, correct_answer, question):
        with Session(self.engine) as session:
            condition = select(MCQModel).where(MCQModel.correct_answer == correct_answer).where(MCQModel.question == question)
            results = session.exec(condition)

            try:
                return results.one()
            except NoResultFound:
                return None
            except MultipleResultsFound:
                print("Multiple results found while getting by details", correct_answer, question)

    def get_by_question(self, question):
        with Session(self.engine) as session:
            condition = select(MCQModel).where(MCQModel.question == question)
            results = session.exec(condition)

            try:
                return results.one()
            except NoResultFound:
                return None
            except MultipleResultsFound:
                print("Multiple results found while getting by question", question)


class QuestionRequest(BaseModel):
    choices: dict[str, str]
    question: str
    website_link: str
    session_token: str

class SummaryRequest(BaseModel):
    text: list[str]


app = FastAPI()
database_access = QuestionDatabaseControl()
request_access = SiteDataRequestManager()

origins = [
    "chrome-extension://pddmfhlahoicjidkahboanogjmhnmeab",
    "moz-extension://pddmfhlahoicjidkahboanogjmhnmeab",
    "https://chatterhigh.com"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ai_api_access = AIAccess()
@app.post("/")
def answer_question(request: QuestionRequest):
    try:
        return ai_api_access.call_answer_question(question=request.question, choices=request.choices,
                                                  link=request.website_link, session_token=request.session_token)
    except TooManyRedirects:
        return "Error! You aren't signed in!"
    except ValueError:
        return "Source was not deemed safe. Aborting question!"
    except Exception as e:
        print("Error!!", e)
@app.post("/summarize")
def summarize_questions(request: SummaryRequest):
    print("Summarizing Questions")
    return convert_to_html(ai_api_access.call_summarizer(documents=request.text))




@app.get("/report_correct_answer")
def add_to_db(question, correct_answer):

    database_access.add(question=question, correct_answer=correct_answer)
    return True

if MODE == "testing":
    if __name__ == "__main__":
        uvicorn.run(app, port=8000, log_level="warning")