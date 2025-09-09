import asyncio
import re
from pathlib import Path

from defusedxml.ElementTree import parse as xmlparse
from tqdm import tqdm

from src.core import config, logger
from src.utils import translator

XML_ESCAPE = str.maketrans(
    {
        '&': '＆',  # noqa: RUF001
        '<': '＜',  # noqa: RUF001
        '>': '＞',  # noqa: RUF001
        '"': '＂',  # noqa: RUF001
        "'": '＇',  # noqa: RUF001
    },
)


log = logger.get('translate')


def replace_xml(xml: str, tag: str, content: str) -> str:
    return re.sub(
        rf'<{tag}>(.*?)</{tag}>',
        f'<{tag}>{content}</{tag}>',
        xml,
        flags=re.DOTALL,
        count=1,
    )


async def translate(xml_text: str) -> str:
    result = await translator.translate(xml_text.replace('<br>', '\n'))
    return result.translate(XML_ESCAPE)


async def process_title(title: str, original_title: str, xml: str) -> str:
    translated_ori_title = await translate(original_title)
    translated_ori_title = translated_ori_title.replace('\n', ' ')
    if original_title in title:  # noqa: SIM108
        new_title = title.replace(original_title, translated_ori_title)
    else:
        new_title = title + ' ' + translated_ori_title
    xml = replace_xml(xml, 'title', new_title)
    xml = replace_xml(xml, 'sorttitle', new_title)
    return insert_tag_below(xml, 'title', 'titletranslated', 'true')


async def process_plot(plot: str, xml: str) -> str:
    new_xml = clone_tag(xml, 'plot', 'originalplot')
    # skip this if failed to copy tag
    if new_xml is None:
        log.error('Plot translation skipped because failed to copy tag')
        return xml
    translated_plot = await translate(plot)
    # cover with CDATA
    translated_plot = f'<![CDATA[{translated_plot.replace("\n", "<br>")}]]>'
    return replace_xml(new_xml, 'plot', translated_plot)


def clone_tag(xml: str, tag: str, new_tag: str) -> str | None:
    pattern = rf'^(\s*)<{tag}>(.*?)</{tag}>'

    # Check if the tag exists first
    if not re.search(pattern, xml, flags=re.DOTALL | re.MULTILINE):
        log.error('Failed to copy tag %s to %s', tag, new_tag)
        return None

    def repl(match: re.Match) -> str:
        indent = match.group(1)
        content = match.group(2)
        return f'{indent}<{tag}>{content}</{tag}>\n{indent}<{new_tag}>{content}</{new_tag}>'

    return re.sub(pattern, repl, xml, flags=re.DOTALL | re.MULTILINE, count=1)


def insert_tag_below(xml: str, tag: str, new_tag: str, content: str) -> str:
    pattern = rf'^(\s*)<{tag}>(.*?)</{tag}>'

    def repl(match: re.Match) -> str:
        indent = match.group(1)
        ori_content = match.group(2)
        return f'{indent}<{tag}>{ori_content}</{tag}>\n{indent}<{new_tag}>{content}</{new_tag}>'

    return re.sub(pattern, repl, xml, flags=re.DOTALL | re.MULTILINE, count=1)


def get_process_list() -> dict[Path, dict[str, str]]:
    process_list = {}
    nfo_dir = config.translate.nfo_dir
    for nfo_path in nfo_dir.glob('**/*.nfo'):
        tree = xmlparse(nfo_path)
        root = tree.getroot()
        title_elem = root.find('title')
        original_title_elem = root.find('originaltitle')
        plot_elem = root.find('plot')
        original_plot_elem = root.find('originalplot')
        title_translated_elem = root.find('titletranslated')
        if title_elem is None:
            log.error('Title not found in %s', nfo_path)
        # check if title need to be translated
        if title_translated_elem is None and original_title_elem is not None:
            process_list[nfo_path] = {
                'title': title_elem.text,
                'original_title': original_title_elem.text,
            }
        # check if plot need to be translated
        if (plot_elem is not None) and plot_elem.text and (original_plot_elem is None):
            if nfo_path not in process_list:
                process_list[nfo_path] = {}
            process_list[nfo_path]['plot'] = plot_elem.text
    return process_list


async def process_one(nfo_path: Path, data: dict[str, str]) -> None:
    log.info('Processing %s', nfo_path)
    xml = nfo_path.read_text()
    if 'title' in data:
        xml = await process_title(data['title'], data['original_title'], xml)
    if 'plot' in data:
        xml = await process_plot(data['plot'], xml)
    nfo_path.with_suffix('.nfo.tmp').write_text(xml)
    nfo_path.with_suffix('.nfo.tmp').rename(nfo_path)


async def batch_process(batch_size: int = 10) -> None:
    log.info('Start NFO translation')
    process_list = get_process_list()
    if not process_list:
        log.info('No items to translate')
        return
    log.info('Found %d items to translate', len(process_list))
    pbar = tqdm(total=len(process_list), desc='Processing')

    semaphore = asyncio.Semaphore(batch_size)

    async def sem_task(nfo_path: Path, data: dict[str, str]) -> None:
        async with semaphore:
            await process_one(nfo_path, data)
            pbar.update(1)

    tasks = [asyncio.create_task(sem_task(nfo_path, data)) for nfo_path, data in process_list.items()]
    await asyncio.gather(*tasks)
    pbar.close()


def main() -> None:
    asyncio.run(batch_process())


if __name__ == '__main__':
    main()
