from kani.engines.openai import OpenAIEngine
from kani.models import ChatMessage
from agent import Participant, Summarizer, Supporter
from constant import TEACHER_INSTRUCTION, STUDENT_INSTRUCTION, SUPPORTER_INSTRUCTION, SUMMARIZER_INSTRUCTION
from datetime import datetime
from pytz import timezone
from copy import deepcopy

import argparse
import random
import asyncio
import os
import json


# Main logic for an actual classroom.
def lecture(args, teacher: Participant, students: Participant, supporter: Supporter, summarizer: Summarizer):
    async def chat():
        turn = 0
        queries = []
        while (turn < args.max_turns):
            # Just for first turn.
            print('-' * 100)
            if turn == 0:
                queries = [ChatMessage.user(f"Generate the introduction of today's lecture topic: {args.topic}")]
                res = await teacher.chat_round_str(queries)
                teacher.chat_history = teacher.chat_history[1:]
                queries = []
            else:
                res = await teacher.chat_round_str(queries)
            print(f"Teacher: {res}")
            print('\n')
            queries.append(ChatMessage.user(name="Teacher", content=res))

            # Classifying whether there should be additional support.
            res = await supporter.check_support(deepcopy(queries))
            if res == 'Yes':
                extensions = await supporter.generate_support(deepcopy(queries))
                print(f"System: {extensions}")
                print('\n')

                better_res = await teacher.chat_round_str([ChatMessage.system(name="Supporter", content=extensions)])
                print(f"Teacher: {better_res}")
                print('\n')

                queries.append(ChatMessage.user(name="Teacher", content=better_res))
            supporter.chat_history.clear()

            student_idxs = list(range(len(students)))
            chosen_idxs = random.sample(student_idxs, random.randint(1, 2))

            for idx in chosen_idxs:
                res = await students[idx].chat_round_str(queries)
                print(f"Student {idx+1}: {res}\n")
                queries.append(ChatMessage.user(name=f"Student-{idx+1}", content=res))

            queries = queries[-len(chosen_idxs):]
            turn += 1

        res = await teacher.chat_round_str(queries)
        print(f"Teacher: {res}")
        print('-' * 100)

        # Summarization of the course.
        score = await summarizer.rate_class(deepcopy(teacher.chat_history))
        print(f"The overall review: {score}")
        print()
        summarizer.chat_history.clear()

        main_points = await summarizer.generate_points(deepcopy(teacher.chat_history))
        print(main_points)
        print()
        summarizer.chat_history.clear()

        improvements = await summarizer.generate_improvements(deepcopy(teacher.chat_history), main_points)
        print(improvements)
        print()
        summarizer.chat_history.clear()

        await teacher.add_to_history(ChatMessage.system(name='Summarizer', content=score))
        await teacher.add_to_history(ChatMessage.system(name='Summarizer', content=main_points))
        await teacher.add_to_history(ChatMessage.system(name='Summarizer', content=improvements))

    loop = asyncio.get_event_loop()
    loop.run_until_complete(chat())
    loop.close()

    # Exporting the data.
    if not os.path.isdir('data'):
        os.makedirs('data')

    history = teacher.chat_history
    logs = [{
        'role': msg.role.value,
        'name': msg.name,
        'content': msg.content
    } for msg in history]

    now = datetime.now(timezone('US/Eastern'))
    execution_time = now.strftime("%Y-%m-%d-%H-%M-%S")

    with open(f"data/seed={args.seed}_model={args.model_idx}_students={args.num_students}_turns={args.max_turns}_topics={args.topic}_time={execution_time}.json", 'w') as f:
        json.dump(logs, f)

if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--seed', type=int, default=555, help="The random seed.")
    parser.add_argument('--model_idx', type=str, default='gpt-4', help="The model index to use.")
    parser.add_argument('--num_students', type=int, default=4, help="The number of students in the class.")
    parser.add_argument('--max_turns', type=int, default=20, help="The maximum number of tuns in a chat.")
    parser.add_argument('--topic', type=str, required=True, help="The specific course topic to discuss.")

    args = parser.parse_args()

    random.seed(args.seed)
    api_key = input("OpenAI API key: ")
    engine = OpenAIEngine(api_key, model=args.model_idx)

    # Teacher Kani.
    system_prompt = ' '.join(TEACHER_INSTRUCTION) + f" The topic is about {args.topic}."
    teacher = Participant(engine=engine, system_prompt=system_prompt)

    # Student Kanis.
    students = []
    for s in range(args.num_students):
        system_prompt = ' '.join(STUDENT_INSTRUCTION) + f" The topic is about {args.topic}."
        student = Participant(engine=engine, system_prompt=system_prompt)
        students.append(student)

    # Supporter Kani.
    system_prompt = ' '.join(SUPPORTER_INSTRUCTION)
    supporter = Supporter(engine=engine, system_prompt=system_prompt)

    # Summarizer Kani.
    system_prompt = ' '.join(SUMMARIZER_INSTRUCTION)
    summarizer = Summarizer(engine=engine, system_prompt=system_prompt)

    # Main logic.
    lecture(args, teacher, students, supporter, summarizer)
