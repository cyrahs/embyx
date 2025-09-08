import asyncio
import re
from pathlib import Path

from defusedxml.ElementTree import parse as xmlparse
from tqdm import tqdm

from src.core import config, logger
from src.utils import get_avid, translator

log = logger.get('translate')


def check_translated_by_title(title: str, original_title: str) -> bool:
    if original_title in title:
        return False
    return re.sub(r'-cd\d+', '', title) != get_avid(title)


def replace_xml(xml: str, tag: str, content: str) -> str:
    # keep CDATA if present
    def repl(m: re.Match) -> str:
        inner = m.group(1)
        if inner.startswith('<![CDATA[') and inner.endswith(']]>'):
            return f'<{tag}><![CDATA[{content}]]></{tag}>'
        return f'<{tag}>{content}</{tag}>'
    return re.sub(
        fr'<{tag}>(.*?)</{tag}>',
        repl,
        xml,
        flags=re.DOTALL,
        count=1,
    )


def duplicate_tag(xml: str, tag: str, new_tag: str) -> str:
    lines = xml.split('\n')
    for i, line in enumerate(lines):
        if re.match(fr'<{tag}>(.*?)</{tag}>', line.strip()):
            new_line = re.sub(fr'<{tag}>(.*?)</{tag}>', fr'<{new_tag}>\1</{new_tag}>', line)
            lines.insert(i+1, new_line)
    return '\n'.join(lines)


async def translate(xml_text: str) -> str:
    if result := re.match(r'<!\[CDATA\[(.*?)\]\]>', xml_text):
        translated_text = await translator.translate(result.group(1))
        return f'<![CDATA[{translated_text}]]>'
    return await translator.translate(xml_text)


async def process_title(title: str, original_title: str, xml: str) -> str:
    translated_ori_title = await translate(original_title)
    if original_title in title:  # noqa: SIM108
        new_title = title.replace(original_title, translated_ori_title)
    else:
        new_title = title + ' ' + translated_ori_title
    xml = replace_xml(xml, 'title', new_title)
    return replace_xml(xml, 'sorttitle', new_title)


async def process_plot(plot: str, xml: str) -> str:
    xml = duplicate_tag(xml, 'plot', 'originalplot')
    translated_plot = await translate(plot)
    return replace_xml(xml, 'plot', translated_plot)


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
        if title_elem is None:
            log.error('Title not found in %s', nfo_path)
        # check if title need to be translated
        if original_title_elem is not None and not check_translated_by_title(title_elem.text, original_title_elem.text):
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


async def main() -> None:
    process_list = get_process_list()
    log.info('%d items to translate', len(process_list))
    pbar = tqdm(total=len(process_list), desc='Processing')

    semaphore = asyncio.Semaphore(10)

    async def sem_task(nfo_path: Path, data: dict[str, str]) -> None:
        async with semaphore:
            await process_one(nfo_path, data)
            pbar.update(1)

    tasks = [asyncio.create_task(sem_task(nfo_path, data)) for nfo_path, data in process_list.items()]
    await asyncio.gather(*tasks)
    pbar.close()


if __name__ == '__main__':
    asyncio.run(main())
