from concurrent.futures import process
from kani import Kani
from kani.engines.openai import OpenAIEngine
from kani.models import ChatMessage
from fastapi import FastAPI
from starlette.websockets import WebSocket, WebSocketDisconnect
from constant import TEACHER_INSTRUCTION, SUPPORTER_INSTRUCTION, SUMMARIZER_INSTRUCTION
from agent import Participant, Supporter, Summarizer
from copy import deepcopy

import uvicorn

SPLIT = '||'
MAX_TURN = 5


app = FastAPI()
api_key = input("OpenAI API key: ")
engine = OpenAIEngine(api_key, model="gpt-4")

# Teacher kani.
system_prompt = ' '.join(TEACHER_INSTRUCTION)
teacher = Participant(engine=engine, system_prompt=system_prompt)

# Supporter Kani.
system_prompt = ' '.join(SUPPORTER_INSTRUCTION)
supporter = Supporter(engine=engine, system_prompt=system_prompt)

# Summarizer Kani.
system_prompt = ' '.join(SUMMARIZER_INSTRUCTION)
summarizer = Summarizer(engine=engine, system_prompt=system_prompt)


def process_messasges(messages: list[ChatMessage]):
    res = []
    for message in messages:
        if message.role.value == 'assistant':
            res.append(ChatMessage.user(name='Teacher', content=message.content))
        else:
            res.append(message)

    return res


@app.websocket("/simulate/{topic}")
async def kani_chat(websocket: WebSocket, topic: str=None):
    # accept the websocket and initialize a kani for the connection
    await websocket.accept()

    # Starting the course.
    res = await teacher.chat_round_str([ChatMessage.user(f"Generate the introduction of today's lecture topic: {topic}.")])
    teacher.chat_history = teacher.chat_history[1:]
    turn = []
    num_turns = 0

    await websocket.send_text(res)
    turn.append(ChatMessage.user(name='Teacher', content=res))

    # take string messages and send string responses
    while True:
        try:
            check = await supporter.check_support(deepcopy(turn))
            if check == 'Yes':
                extensions = await supporter.generate_support([])
                await websocket.send_text(extensions)

                better_res = await teacher.chat_round_str([ChatMessage.system(name='Supporter', content=extensions)])
                await websocket.send_text(better_res)

            turn.clear()

            texts = await websocket.receive_text()
            for text in texts.split('||'):
                turn.append(ChatMessage.user(name='Student', content=text))

            res = await teacher.chat_round_str(turn)
            await websocket.send_text(res)
            turn.append(ChatMessage.user(name='Teacher', content=res))

            num_turns += 1
            if num_turns == MAX_TURN:
                class_logs = process_messasges(teacher.chat_history)

                # Review.
                review = await summarizer.rate_class(class_logs)
                await websocket.send_text(review)

                # Main points.
                main_points = await summarizer.generate_points([])
                await websocket.send_text(main_points)

                # Improvements.
                improvements = await summarizer.generate_improvements([], main_points)
                await websocket.send_text(improvements)

                break

        # until the client disconnects
        except WebSocketDisconnect:
            return


@app.on_event("shutdown")
async def cleanup_kani():
    """When the application shuts down, cleanly close the kani engine."""
    await engine.close()


uvicorn.run(app)
