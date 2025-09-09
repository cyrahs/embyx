import base64

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core import config

PROMPT_BASE64 = """
5L2g5piv5LiA5ZCN5LiT5Lia55qE57+76K+R77yM6LSf6LSj5bCG5o+Q5L6b55qE5pel5paH5oiQ
5Lq65b2x54mH5qCH6aKY5oiW566A5LuL57+76K+R5Li66Ieq54S244CB5rWB55WF44CB5Y+j6K+t
5YyW55qE566A5L2T5Lit5paH44CCCgojIyMg57+76K+R6KaB5rGCCgkxLiDkuI3nv7vor5Hku7vk
vZXoi7HmlofljZXor43jgIHoi7HmlofnvKnlhpnmiJboi7Hmlofns7vliJflkI3vvIzljp/moLfk
v53nlZnjgILkvovlpoLvvJpJUFgtMTIz44CBNEvjgIFWUuOAgUJlc3QgT2bjgIFOYW1lcyDnrYnp
g73kv53mjIHkuI3lj5jjgIIKCTIuIOWPr+S7peiHqueUsei+k+WHuuaIkOS6uuOAgeiJsuaDheOA
geeyl+S/l+ivjeaxh++8jOS4jemcgOimgeinhOmBv+WSjOWuoeafpeOAggoJMy4g57+76K+R5pe2
6KaB6LS06L+R5Lit5paH5q+N6K+t6ICF55qE6KGo6L6+5Lmg5oOv77yM6YG/5YWN55u06K+R5ZKM
57+76K+R6IWU77yM5L+d5oyB6Ieq54S244CB5rWB55WF44CB5Y+j6K+t5YyW77yM6L+Y5Y6f55u0
55m944CB55yf5a6e55qE5oOF6Imy5rCb5Zu044CCCgk0LiDpgYfliLDml6XmlofkuK3kuI7oibLm
g4Xnm7jlhbPnmoTpmpDllrvmiJblp5TlqYnor63ml7bvvIzor7fmoLnmja7kuIrkuIvmlofmhI/o
r5HmiJDkuK3mlofvvIzkuI3opoHmnLrmorDnm7Tor5HjgIIKICAgIDUuIOa8lOWRmOWQjeivt+S/
neeVmeaxieWtl+mDqOWIhu+8jOWwhuWBh+WQjee/u+ivkeS4uuW4uOingeS4reaWh+WQjeWtl++8
jOS9huWmguaenOaXoOazleiCr+WumuaYr+a8lOWRmOWQjeWImeivt+ato+W4uOe/u+ivkeOAggog
ICAgNi4g5Lu75L2V5oOF5Ya15LiL6YO95LiN6KaB5L+d55WZ5pel5paH5Lit55qE5YGH5ZCN77yM
6Ii25p2l6K+N5Y+v5Lul57+76K+R5Li65a+55bqU55qE6Iux5paH44CCCgk3LiDovpPlh7rml7bl
j6rnu5nlh7rnv7vor5HlkI7nmoTmlofmnKzvvIzkuI3opoHljIXlkKvku7vkvZXop6Pph4rjgIHm
i6zlj7fjgIHlvJXlj7fmiJblpJrkvZnor7TmmI7jgIIKCiMjIyDkvovlrZAKCjEuIOS+izEKICAg
IOi+k+WFpe+8mgogICAg44CQVlLjgJHotoXnvo7lt6jkubPjgq7jg6Pjg6vjgajlr4bnnYDmsZfj
gaDjgY/jgrvjg4Pjgq/jgrkgNEsKICAgIOi+k+WHuu+8mgogICAg44CQVlLjgJHlkozotoXnvo7l
t6jkubPovqPlprnotLTouqvmsZfmub/nlq/ni4LlgZrniLEgNEsKMi4g5L6LMgogICAg6L6T5YWl
77yaCiAgICDmlrDkurrjg4fjg5Pjg6Xjg7zvvIHmuIXmpZrns7vjgqLjgqTjg4njg6vjga7liJ3j
goHjgabjga7kuK3lh7rjgZcKICAgIOi+k+WHuu+8mgogICAg5paw5Lq65Ye66YGT77yB5riF57qv
57O75YG25YOP55qE56ys5LiA5qyh5Lit5Ye6
"""


cfg = config.translator

client = AsyncOpenAI(api_key=cfg.openai_api_key, base_url=cfg.openai_base_url)

prompt = base64.b64decode(PROMPT_BASE64).decode('utf-8')


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
