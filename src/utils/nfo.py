"""Nfo module."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING

from defusedxml.ElementTree import parse as xmlparse
from pydantic import BaseModel

from src.core import logger

if TYPE_CHECKING:
    from pathlib import Path

log = logger.get('nfo')

class Nfo(BaseModel):
    path: Path
    date: str | None
    duration: int | None
    title: str
    sort_title: str
    original_title: str
    plot: str | None

class NfoOld:
    def __init__(self, file_path: Path) -> None:
        """Init Nfo."""
        self.path = file_path
        if not self.path.exists():
            msg = f'{self.path} not found'
            raise FileNotFoundError(msg)
        try:
            self.tree = xmlparse(self.path)
            self.root = self.tree.getroot()
            # load elements
            date_elem = self.root.find('premiered')
            self.date: str | None = date_elem.text if date_elem else None
            duration_elem = self.root.find('runtime') or self.root.find('duration')
            duration_text = duration_elem.text if duration_elem else None
            self.duration: int | None = int(duration_text) if duration_text else None
        except Exception:
            log.exception('Failed to init Nfo %s', self.path)
            raise

    def __repr__(self) -> str:
        """Nfo representation."""
        return f'{self.path}'

    @property
    def title(self) -> str:
        """Title in NFO."""
        elem = self.tree.find('title')
        if elem is None or elem.text is None:
            self.title = self.id
            return self.id
        return elem.text

    @title.setter
    def title(self, value: str) -> None:
        """Set title in NFO."""
        elem = self.tree.find('title')
        if elem is None:
            elem = ET.Element('title')
            self.root.insert(0, elem)
        elem.text = value

    @property
    def plot(self) -> str | None:
        """Plot in NFO."""
        elem = self.tree.find('plot')
        if elem is None:
            return None
        return elem.text

    @plot.setter
    def plot(self, value: str) -> None:
        """Set plot in NFO."""
        elem = self.tree.find('plot')
        if elem is None:
            elem = ET.Element('plot')
            self.root.append(elem)
        elem.text = value

    @property
    def genres(self) -> list[str | None]:
        """Genres in NFO."""
        elems = self.tree.findall('genre')
        return [i.text for i in elems]

    @genres.setter
    def genres(self, value: list[str]) -> None:
        """Set genres in NFO."""
        if len(value) != len(self.genres):
            msg = 'Length of genres must be the same'
            raise ValueError(msg)
        elems = self.tree.findall('genre')
        for i, text in enumerate(value):
            elems[i].text = text

    @property
    def tags(self) -> list[str | None]:
        """Tags in NFO."""
        elems = self.tree.findall('tag')
        return [i.text for i in elems]

    @tags.setter
    def tags(self, value: list[str]) -> None:
        """Set tags in NFO."""
        if len(value) != len(self.tags):
            msg = 'Length of tags must be the same'
            raise ValueError(msg)
        elems = self.tree.findall('tag')
        for i, text in enumerate(value):
            elems[i].text = text

    @property
    def actors(self) -> list[str]:
        """Actors in NFO."""
        elems = self.tree.findall('actor')
        if not elems:
            return ['Unknown']
        result = []
        for elem in elems:
            name = elem.find('name')
            if name is None:
                msg = 'Actor name not found'
                raise ValueError(msg)
            result.append(name.text)
        return result

    @actors.setter
    def actors(self, value: list[str]) -> None:
        """Set actors in NFO."""
        if len(value) != len(self.actors):
            msg = 'Length of actors must be the same'
            raise ValueError(msg)
        elems = self.tree.findall('actor')
        for i, text in enumerate(value):
            elem = elems[i]
            name = elem.find('name')
            if name is None:
                name = ET.Element('name')
                elem.append(name)
            name.text = text

    @property
    def avid(self) -> str | None:
        """Avid in NFO."""
        elem = self.tree.find("uniqueid[@type='num']")
        if elem is None:
            return None
        return elem.text

    @avid.setter
    def avid(self, value: str) -> None:
        """Set avid in NFO."""
        elem = self.tree.find("uniqueid[@type='num']")
        if elem is None:
            elem = ET.Element('uniqueid')
            elem.set('type', 'num')
            self.root.append(elem)
        elem.text = value

    def save(self) -> None:
        """Save NFO."""
        self.tree.write(self.path, encoding='utf-8', xml_declaration=True)
