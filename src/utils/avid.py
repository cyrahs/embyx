"""获取和转换影片的各类番号(DVD ID, DMM cid, DMM pid)"""
import re
from pathlib import Path

from src.core import config

cfg = config.avid
MIN_BRAND_LENGTH = 2


def get_avid(title: str) -> str:
    title = title.replace('/', '')
    for s in cfg.get_id_exceptions:
        if s in title.upper():
            return s
    return get_id(title).upper()

def get_brand(avid: str) -> str | None:
    if '-' not in avid:
        return None
    brand = avid.split('-')[0]
    if re.match(r'^\d+$', brand) and len(brand) >= MIN_BRAND_LENGTH:
        brand = brand[:MIN_BRAND_LENGTH]
    return brand

def get_cd(title: str) -> str | None:
    if result := re.search(r'CD(\d+).', title):
        return result.group(1)
    return None


def get_id(filepath_str: str) -> str:  # noqa: C901, PLR0911, PLR0912
    """从给定的文件路径中提取番号(DVD ID)"""
    filepath = Path(filepath_str)
    # 通常是接收文件的路径, 当然如果是普通字符串也可以
    ignore_pattern = re.compile('|'.join(cfg.ignored_id_pattern))
    norm = ignore_pattern.sub('', filepath.stem).upper()
    if 'FC2' in norm:
        # 根据FC2 Club的影片数据, FC2编号为5-7个数字
        match = re.search(r'FC2[^A-Z\d]{0,5}(PPV[^A-Z\d]{0,5})?(\d{5,7})', norm, re.IGNORECASE)
        if match:
            return 'FC2-' + match.group(2)
    elif 'HEYDOUGA' in norm:
        match = re.search(r'(HEYDOUGA)[-_]*(\d{4})[-_]0?(\d{3,5})', norm, re.IGNORECASE)
        if match:
            return '-'.join(match.groups())
    elif 'GETCHU' in norm:
        match = re.search(r'GETCHU[-_]*(\d+)', norm, re.IGNORECASE)
        if match:
            return 'GETCHU-' + match.group(1)
    elif 'GYUTTO' in norm:
        match = re.search(r'GYUTTO-(\d+)', norm, re.IGNORECASE)
        if match:
            return 'GYUTTO-' + match.group(1)
    elif '259LUXU' in norm:  # special case having form of '259luxu'
        match = re.search(r'259LUXU-(\d+)', norm, re.IGNORECASE)
        if match:
            return '259LUXU-' + match.group(1)

    else:
        # 先尝试移除可疑域名进行匹配, 如果匹配不到再使用原始文件名进行匹配
        no_domain = re.sub(r'\w{3,10}\.(COM|NET|APP|XYZ)', '', norm, flags=re.IGNORECASE)
        if no_domain != norm:
            avid = get_avid(no_domain)
            if avid:
                return avid
        # 匹配缩写成hey的heydouga影片。由于番号分三部分, 要先于后面分两部分的进行匹配
        match = re.search(r'(?:HEY)[-_]*(\d{4})[-_]0?(\d{3,5})', norm, re.IGNORECASE)
        if match:
            return 'heydouga-' + '-'.join(match.groups())
        # 匹配片商 MUGEN 的奇怪番号。由于MK3D2DBD的模式, 要放在普通番号模式之前进行匹配
        match = re.search(r'(MKB?D)[-_]*(S\d{2,3})|(MK3D2DBD|S2M|S2MBD)[-_]*(\d{2,3})', norm, re.IGNORECASE)
        if match:
            return match.group(1) + '-' + match.group(2) if match.group(1) is not None else match.group(3) + '-' + match.group(4)
        # 匹配IBW这样带有后缀z的番号
        match = re.search(r'(IBW)[-_](\d{2,5}z)', norm, re.IGNORECASE)
        if match:
            return match.group(1) + '-' + match.group(2)
        # 普通番号, 优先尝试匹配带分隔符的, 如ABC-123
        match = re.search(r'([A-Z]{2,10})[-_](\d{2,5})', norm, re.IGNORECASE)
        if match:
            return match.group(1) + '-' + match.group(2)
        # 普通番号, 运行到这里时表明无法匹配到带分隔符的番号
        # 先尝试匹配东热的red, sky, ex三个不带-分隔符的系列
        # 这三个系列已停止更新, 因此根据其作品编号将数字范围限制得小一些以降低误匹配概率
        match = re.search(r'(RED[01]\d\d|SKY[0-3]\d\d|EX00[01]\d)', norm, re.IGNORECASE)
        if match:
            return match.group(1)
        # 然后再将影片视作缺失了-分隔符来匹配
        match = re.search(r'([A-Z]{2,})(\d{2,5})', norm, re.IGNORECASE)
        if match:
            return match.group(1) + '-' + match.group(2)
    # 尝试匹配TMA制作的影片(如'T28-557', 他家的番号很乱)
    match = re.search(r'(T[23]8[-_]\d{3})', norm)
    if match:
        return match.group(1)
    # 尝试匹配东热n, k系列
    match = re.search(r'(N\d{4}|K\d{4})', norm, re.IGNORECASE)
    if match:
        return match.group(1)
    # 尝试匹配纯数字番号, 无码影片
    match = re.search(r'(\d{6}[-_]\d{2,3})', norm)
    if match:
        return match.group(1)
    # 如果还是匹配不了, 尝试将')('替换为'-'后再试, 少部分影片的番号是由')('分隔的
    if ')(' in norm:
        avid = get_avid(norm.replace(')(', '-'))
        if avid:
            return avid
    # 如果最后仍然匹配不了番号, 则尝试使用文件所在文件夹的名字去匹配

    if filepath.parent.name != '':  # haven't reach '.' or '/'
        return get_avid(filepath.parent.name)
    return ''

