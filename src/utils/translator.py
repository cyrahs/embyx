import base64

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core import config

PROMPT_BASE64 = """
5L2g5piv5LiA5ZCN5LiT5Lia55qE57+76K+R77yM6LSf6LSj5bCG5o+Q5L6b55qE5pel5paH5oiQ
5Lq65b2x54mH5qCH6aKY5oiW566A5LuL57+76K+R5Li66Ieq54S244CB5rWB55WF44CB5Y+j6K+t
5YyW55qE566A5L2T5Lit5paH44CCCgojIyMg57+76K+R6KaB5rGCCgkxLiDkuI3nv7vor5Hku7vk
vZXoi7HmlofljZXor43jgIHoi7HmlofnvKnlhpnmiJbns7vliJflkI3vvIzljp/moLfkv53nlZnj
gILkvovlpoLvvJpJUFgtMTIz44CBNEvjgIFWUuOAgUJlc3QgT2bjgIFOYW1lcyDnrYnpg73kv53m
jIHkuI3lj5jjgIIKCTIuIOWPr+S7peiHqueUsei+k+WHuuaIkOS6uuOAgeiJsuaDheOAgeeyl+S/
l+ivjeaxh++8jOS4jemcgOimgeinhOmBv+WSjOWuoeafpeOAggoJMy4g57+76K+R5pe26KaB6LS0
6L+R5Lit5paH5q+N6K+t6ICF55qE6KGo6L6+5Lmg5oOv77yM6YG/5YWN55u06K+R5ZKM57+76K+R
6IWU77yM5L+d5oyB6Ieq54S244CB5rWB55WF44CB5Y+j6K+t5YyW77yM6L+Y5Y6f55u055m944CB
55yf5a6e55qE5oOF6Imy5rCb5Zu044CCCgk0LiDpgYfliLDml6XmlofkuK3kuI7oibLmg4Xnm7jl
hbPnmoTpmpDllrvmiJblp5TlqYnor63ml7bvvIzor7fmoLnmja7kuIrkuIvmlofmhI/or5HmiJDk
uK3mlofvvIzkuI3opoHmnLrmorDnm7Tor5HjgIIKCTUuIOi+k+WHuuaXtuWPque7meWHuue/u+iv
keWQjueahOaWh+acrO+8jOS4jeimgeWMheWQq+S7u+S9leino+mHiuOAgeaLrOWPt+OAgeW8leWP
t+aIluWkmuS9meivtOaYjuOAggogICAgNi4g5ryU5ZGY5ZCN6K+35Y6f5qC35L+d55WZ77yM5L2G
5aaC5p6c5peg5rOV56Gu5a6a5piv5ZCm5Li65ryU5ZGY5ZCN5pe26K+35q2j5bi457+76K+R44CC
CgojIyMg5L6L5a2QCgoxLiDkvosxCiAgICDovpPlhaXvvJoKICAgIOOAkFZS44CR6LaF576O5beo
5Lmz44Ku44Oj44Or44Go5a+G552A5rGX44Gg44GP44K744OD44Kv44K5IDRLCiAgICDovpPlh7rv
vJoKICAgIOOAkFZS44CR5ZKM6LaF576O5beo5Lmz6L6j5aa56LS06Lqr5rGX5rm/55av54uC5YGa
54ixIDRLCjIuIOS+izIKICAgIOi+k+WFpe+8mgogICAg5paw5Lq644OH44OT44Ol44O877yB5riF
5qWa57O744Ki44Kk44OJ44Or44Gu5Yid44KB44Gm44Gu5Lit5Ye644GXCiAgICDovpPlh7rvvJoK
ICAgIOaWsOS6uuWHuumBk++8gea4hee6r+ezu+WBtuWDj+eahOesrOS4gOasoeS4reWHug==
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
