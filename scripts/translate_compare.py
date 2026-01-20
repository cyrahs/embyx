import asyncio
import base64
import csv
import random
from pathlib import Path

from defusedxml.ElementTree import parse as xmlparse
from openai import AsyncOpenAI, OpenAIError
from tqdm import tqdm

from src.core import config, logger

log = logger.get('translate_compare')


# Copy prompt from translator.py
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

PROMPT = base64.b64decode(PROMPT_BASE64).decode('utf-8')

# Models to test
MODELS = [
    'google/gemini-2.5-flash',
    'google/gemma-3-27b-it',
    'deepseek/deepseek-chat-v3.1',
    'x-ai/grok-4-fast',
    'meta-llama/llama-4-8b-instruct',
    'openai/gpt-5-nano',
    'meta-llama/llama-4-maverick',
    'qwen/qwen3-32b',
]


async def get_japanese_titles(nfo_dir: Path, limit: int = 100) -> list[tuple[str, str]]:
    """
    Scan for NFO files and extract japanese original titles.
    Returns list of (filename, original_title).
    """
    titles = []
    nfos = list(nfo_dir.rglob('*.nfo'))
    random.shuffle(nfos)  # Randomize to get a mix

    log.info('Found %d nfo files. Processing...', len(nfos))

    count = 0
    for nfo_path in tqdm(nfos):
        if count >= limit:
            break
        try:
            tree = xmlparse(nfo_path)
            root = tree.getroot()

            # Try to get originaltitle
            orig_title_elem = root.find('originaltitle')
            if orig_title_elem is not None and orig_title_elem.text:
                titles.append((nfo_path.name, orig_title_elem.text))
                count += 1
                continue

            # If no originaltitle, check if title contains japanese chars (simple heuristic? No, just skip)
            # Or assume title might be japanese if originaltitle is missing?
            # Let's stick to files with originaltitle to be safe.

        except Exception:
            log.exception('Error parsing %s', nfo_path)
            continue

    return titles


async def translate_text(client: AsyncOpenAI, model: str, text: str) -> str:
    try:
        completion = await client.chat.completions.create(
            model=model,
            messages=[
                {'role': 'system', 'content': PROMPT},
                {'role': 'user', 'content': text},
            ],
            temperature=0,
        )
        tqdm.write(f'{model}: {completion.choices[0].message.content}')
        return completion.choices[0].message.content
    except (OpenAIError, TimeoutError) as e:
        return f'Error: {e!s}'


def write_comparison(output_file: Path, header: list[str], results: list[dict[str, str]]) -> None:
    with output_file.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        writer.writerows(results)

    log.info('Comparison saved to %s', output_file.absolute())


async def main() -> tuple[list[str], list[dict[str, str]], Path] | None:
    cfg = config.translator
    # Use config from codebase
    client = AsyncOpenAI(api_key=cfg.openai_api_key, base_url=cfg.openai_base_url)

    nfo_dir = Path('/root/media/embyx/local/actor/clt')
    if not nfo_dir.exists():
        log.error('Directory %s does not exist.', nfo_dir)
        return None

    log.info('Loading titles...')
    titles = await get_japanese_titles(nfo_dir, limit=100)
    log.info('Loaded %d titles.', len(titles))

    results = []

    # Header
    header = ['Filename', 'Original Title', *MODELS]

    # Process translations
    log.info('Translating...')
    for filename, jp_title in tqdm(titles):
        row = {'Filename': filename, 'Original Title': jp_title}

        # Parallelize translation for each model? No, let's keep it simple sequential per title or parallel per title
        # Let's run all models for this title in parallel
        tasks = [translate_text(client, model, jp_title) for model in MODELS]
        translations = await asyncio.gather(*tasks)

        row.update(dict(zip(MODELS, translations, strict=True)))

        results.append(row)

    # Save to CSV
    output_file = Path('translation_comparison.csv')
    return header, results, output_file


if __name__ == '__main__':
    comparison = asyncio.run(main())
    if comparison is not None:
        header, results, output_file = comparison
        write_comparison(output_file, header, results)
