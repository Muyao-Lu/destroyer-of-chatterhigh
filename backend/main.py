from typing import Optional

from groq import Groq, RateLimitError, APIStatusError
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_hyperbrowser import HyperbrowserLoader
import dotenv, os, json, cohere
import uvicorn
import requests
import time, datetime
from sqlmodel import SQLModel, Field, create_engine, Session, select
from sqlalchemy.exc import NoResultFound

dotenv.load_dotenv()

MODE = "deployment"

assert MODE == "testing" or MODE == "deployment"


def get_final_url(url, session_token):
    begin = datetime.datetime.now()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://chatterhigh.com/"
    }

    response = requests.get(url=url, headers=headers, cookies={"_chatterhigh_session_1": session_token})
    print("Got final url with time of", (datetime.datetime.now() - begin).total_seconds())

    return response.url

class Scraper:
    def __init__(self):
        self.api_key = os.environ["HYPERBROWSER_API_KEY"]

    def scrape(self, link):
        loader = HyperbrowserLoader(
            urls=link,
            api_key=self.api_key
        )

        r = loader.load()

        return r[0].page_content

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
            chunk_size=300,
            chunk_overlap=100
        )
        self.model = "groq/compound"
        self.embedding_model = cohere.ClientV2()
        with open("prompts.json", "r") as p:
            self.json_file = json.load(p)
        self.REPEAT_LIMIT = 5

    def find_top_segment(self, query, document):
        segments = self.splitter.split_text(document)

        results = self.embedding_model.rerank(
            model="rerank-v3.5",
            query=query,
            documents=segments,
            top_n=1,
        )

        results = dict(results)

        first_item_data = dict(results["results"][0])
        return first_item_data


    def generate_fast_prompt(self, question, choices, link, session_token):
        prompt = self.json_file["answer_quiz"].format(question=question, choices=choices, link=get_final_url(link, session_token))
        return prompt

    def generate_rag_prompt(self, question, choices, link, session_token):
        t = self.find_top_segment(query=question, document=self.scraper.scrape(link=get_final_url(link, session_token)))
        prompt = self.json_file["answer_quiz_long"].format(question=question, choices=choices, excerpt=t, source=link)
        return prompt

    def call_ai(self, question, choices: dict, link, session_token):
        reverse_choices = dict((choices[key], key) for key in choices.keys())
        for key in choices.keys():
            result = database_access.get_by_details(correct_answer=choices[key], question=question)
            if result is not None:
                try:
                    return reverse_choices[result.correct_answer]
                except KeyError:
                    continue

        p = self.generate_fast_prompt(question=question, choices=choices, link=link, session_token=session_token)
        repeats = 0
        messages = [
            {
                'role': 'user',
                'content': p,

            },
        ]
        tools = {"tools":{"enabled_tools":["visit_website","web_search"]}}
        begin = datetime.datetime.now()
        while repeats < self.REPEAT_LIMIT:
            repeats += 1

            try:

                res = self.text_gen_model.chat.completions.create(
                    model=self.model,
                    temperature=0.5,
                    messages=messages,
                    compound_custom=tools)
                print("Called ai with a time of:", (datetime.datetime.now() - begin).total_seconds())
                print("Result", res)
                return res.choices[0].message.content
            except RateLimitError as e:
                print("Rate limit hit", e)
                time.sleep(2**repeats)
            except APIStatusError:
                p = self.generate_rag_prompt(question=question, choices=choices, link=link,
                                             session_token=session_token)
                messages = [
                    {
                        'role': 'user',
                        'content': p,

                    },
                ]
                tools = {}


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

    def get_by_details(self, correct_answer, question):
        with Session(self.engine) as session:
            condition = select(MCQModel).where(MCQModel.correct_answer == correct_answer and MCQModel.question == question)
            results = session.exec(condition)

            try:
                return results.one()
            except NoResultFound:
                return None


class QuestionRequest(BaseModel):
    choices: dict[str, str]
    question: str
    website_link: str
    session_token: str

app = FastAPI()
database_access = QuestionDatabaseControl()

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
    print("request post")
    return ai_api_access.call_ai(question=request.question, choices=request.choices,
                                 link=request.website_link, session_token=request.session_token)

@app.get("/report_correct_answer")
def add_to_db(question, correct_answer):

    print("request add_to_db")
    database_access.add(question=question, correct_answer=correct_answer)
    return True

if MODE == "testing":
    if __name__ == "__main__":
        uvicorn.run(app, port=8000)