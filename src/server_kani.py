from kani.models import ChatMessage
from kani.engines.openai import OpenAIEngine
from fastapi import FastAPI, Query
from agent import Supporter, Summarizer
from constant import SUPPORTER_INSTRUCTION, SUMMARIZER_INSTRUCTION

import uvicorn

SPLIT = '||'

app = FastAPI()
api_key = input("OpenAI API key: ")
engine = OpenAIEngine(api_key, model="gpt-4")

# Supporter Kani.
system_prompt = ' '.join(SUPPORTER_INSTRUCTION)
supporter = Supporter(engine=engine, system_prompt=system_prompt)

# Summarizer Kani.
system_prompt = ' '.join(SUMMARIZER_INSTRUCTION)
summarizer = Summarizer(engine=engine, system_prompt=system_prompt)


def process_queries(queries: list[str]):
    messages = []
    for query in queries:
        first, second = query.split(SPLIT)
        if first.lower() == 'teacher':
            messages.append(ChatMessage.user(name="Teacher", content=second.strip()))
        elif first.lower() == 'system':
            messages.append(ChatMessage.system(name='Supporter', content=second.strip()))
        else:
            messages.append(ChatMessage.user(name=first, content=second.strip()))
    
    return messages


@app.get("/checksupport/")
async def check_support(queries: list[str] = Query(None)):
    messages = process_queries(queries)
    res = await supporter.check_support(messages)

    return {'support': True} if res == 'Yes' else {'support': False}


@app.get("/extensions/")
async def generate_extensions():
    # Note that this is only exectued after running GET /checksupport.
    extensions = await supporter.generate_support([])

    return {'extensions': extensions}


@app.get("/rate/")
async def rate_class(queries: list[str] = Query(None)):
    messages = process_queries(queries)
    score = await summarizer.rate_class(messages)

    return {'rate': score}


@app.get("/mainpoints/")
async def generate_points():
    # Note that this is only exectued after running GET /rate.
    main_points = await summarizer.generate_points([])

    return {'main_points': main_points}


@app.get("/improvements/")
async def generate_improvements(mainpoints: str=None):
    # Note that this is only exectued after running GET /improvements.
    improvements = await summarizer.generate_improvements([], mainpoints)

    return {'improvements': improvements}


@app.on_event("shutdown")
async def cleanup_kani():
    """When the application shuts down, cleanly close the kani engine."""
    await engine.close()


uvicorn.run(app)