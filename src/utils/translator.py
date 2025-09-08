from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core import config

cfg = config.translator

client = AsyncOpenAI(api_key=cfg.openai_api_key, base_url=cfg.openai_base_url)

prompt = cfg.prompt_file.read_text()


def check_valid(text: str) -> bool:
    excemption_length = 30
    if not text.startswith(('抱歉', '对不起')):
        return True
    if len(text) > excemption_length:
        return True
    return not (any(['无法' in text, '不能' in text, '失败' in text]) and '请求' in text)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
async def chat(model: str, prompt: str, text: str) -> str:
    message = [
        {'role': 'system', 'content': prompt},
        {'role': 'user', 'content': text},
    ]
    temperature = 0
    completion = await client.chat.completions.create(
        model=model,
        messages=message,
        temperature=temperature,
    )
    return completion.choices[0].message.content


async def translate(content: str) -> str:
    model_list = cfg.model_list
    # check result
    for model in model_list:
        result = await chat(model, prompt, content)
        if result is None:
            continue
        if not check_valid(result):
            continue
        return result
    msg = 'All translator refused to translate, please check nfo content'
    raise ValueError(msg)
