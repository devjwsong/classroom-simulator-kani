from kani import Kani
from kani.models import ChatMessage

import re
import random


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


class Paritipant(Kani):
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


class Supporter(Paritipant):
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
