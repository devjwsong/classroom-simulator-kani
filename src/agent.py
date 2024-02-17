from copy import deepcopy
from typing import Annotated
from kani import Kani
from kani.engines.httpclient import BaseClient
from kani.models import ChatMessage

import re
import random
import json


class WikiClient(BaseClient):
    SERVICE_BASE = "https://en.wikipedia.org/w/api.php"


# Extracting the class index in the output of a classification problem.
def convert_into_class_idx(res: str, options: list):
    pattern = r'\d+'
    matches = re.findall(pattern, res)
    if matches:
        index = int(matches[0])
        if index >= len(options):
            return random.choice(list(range(len(options))))
        return index
    else:
        return random.choice(list(range(len(options))))


class Participant(Kani):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def chat_round(self, queries: list[ChatMessage], **kwargs) -> ChatMessage:
        """Perform a single chat round (user -> model -> user, no functions allowed).

        This is slightly faster when you are chatting with a kani with no AI functions defined.

        :param query: The contents of the user's chat message.
        :param kwargs: Additional arguments to pass to the model engine (e.g. hyperparameters).
        :returns: The model's reply.
        """
        kwargs = {**kwargs, "include_functions": False}
        # do the chat round
        async with self.lock:
            # add the user's chat input to the state
            for msg in queries:
                await self.add_to_history(msg)

            # and get a completion
            completion = await self.get_model_completion(**kwargs)
            message = completion.message
            await self.add_to_history(message)
            return message

    async def chat_round_str(self, queries: list[ChatMessage], **kwargs) -> str:
        """Like :meth:`chat_round`, but only returns the text content of the message."""
        msg = await self.chat_round(queries, **kwargs)
        return msg.text


class Supporter(Participant):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def check_support(self, queries: list[ChatMessage]):
        options = ['Yes', 'No']
        options_str = '\n'.join([f"{o}: {option}" for o, option in enumerate(options)])
        queries.append(ChatMessage.system(content=f"Do you think the teacher's answer needs some support or not? You should answer only in number.\n\n{options_str}"))

        res = await self.chat_round_str(queries)
        res = convert_into_class_idx(res, options)

        return options[res]

    async def generate_support(self, queries: list[ChatMessage]):
        query = "Suggest about 2-3 additional subtopics or extensions you think useful for the teacher to help the students understand better.\n\nYour answer should start with: 'It might be great to explain more about...' and then the list of suggestions."
        queries.append(ChatMessage.system(content=query))

        res = await self.chat_round_str(queries)
        return res


class Summarizer(Participant):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def rate_class(self, queries: list[ChatMessage]):
        query = "Rate the overall quality of the lecture in terms of the quality of the content and how detailed and understandable the teacher's explanation is. You should generate the score between 1 to 10 and a brief reason in one sentence."
        queries.append(ChatMessage.system(content=query))

        res = await self.chat_round_str(queries)
        return res

    async def generate_points(self, queries: list[ChatMessage]):
        query = "Generate 2-3 essential subtopics or contents during the class. These could be the ones which most students were curious about or which you think as the important contents to refer to for improving the course quality in the future. Your answer should start with: 'The main points of today's class: ' and then the list of contents. Each item should be as simple as possible."
        queries.append(ChatMessage.system(content=query))

        res = await self.chat_round_str(queries)
        return res

    async def generate_improvements(self, queries: list[ChatMessage], main_points: str):
        query = f"Generate your recommendation to the teacher so that the course quality can be improve next time based on the suggested main points of the class. You should only give recommendations without any additional ratings or repetition of main points.\n\n{main_points}"
        queries.append(ChatMessage.system(content=query))

        res = await self.chat_round_str(queries)
        return res


class PersonalizedTutor(Participant):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.wiki_client = WikiClient()

    async def search_articles(self, query: str):
        """
        If there is a specific topic to search in Wiki,
        call this function with the query string.
        """

        resp = await self.wiki_client.get(
            "/",
            params={"action": "opensearch", "format": "json", "search": query}
        )

        if resp[1] is not None:
            return resp[1]
        return None

    async def search_content(self, title: str):
        resp = await self.wiki_client.get(
            "/",
            params={
                "action": "query",
                "format": "json",
                "prop": "extracts",
                "titles": title,
                "explaintext": 1,
                "formatversion": 2,
            },
        )
        page = resp["query"]["pages"][0]
        if extract := page.get("extract"):
            return extract

    async def generate_help(self, name: str, background: str, queries: list[ChatMessage]):
        query = f"Generate one topic word which would be most helpful to the student {name}. If there is none, just generate 'None'.\n\nStudent background: {background}."
        topic = await self.chat_round_str(queries + [ChatMessage.system(content=query)])

        if 'None' not in topic:
            titles = await self.search_articles(topic)

            if titles is not None and len(titles) > 0:
                content = await self.search_content(titles[0])
                query = f"Generate the summarization of given article in 2-3 sentences to help the student.\n\n{content[:1000]}"
                res = await self.chat_round_str([ChatMessage.system(content=query)])
                return res
