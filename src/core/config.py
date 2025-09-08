from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict, TomlConfigSettingsSource


class Avid(BaseModel):
    get_id_exceptions: list[str]
    ignored_id_pattern: list[str]
    brand_mapping: dict[str, str]


class Archive(BaseModel):
    mapping: dict[Path, Path]
    min_size: int
    src_dir: Path
    dst_dir: Path
    brand_mapping: dict[str, list[str]]


class Mapping(BaseModel):
    src_dir: Path
    dst_dir: Path


class Translate(BaseModel):
    nfo_dir: Path


class Translator(BaseModel):
    openai_api_key: str
    openai_base_url: str
    model_list: list[str]
    prompt_file: Path


class Freshrss(BaseModel):
    freshrss_url: str
    freshrss_api_key: str
    proxy: str


class Rss(BaseModel):
    rsshub_url: str
    cf_access_client_id: str
    cf_access_client_secret: str
    open115_url: str
    task_dir_id: str


class Emby(BaseModel):
    url: str
    api_key: str
    user_id: str


class FillActor(BaseModel):
    actor_brand_path: Path
    additional_brand_path: list[Path]
    move_in_path: Path


class Config(BaseSettings):
    avid: Avid
    archive: Archive
    mapping: Mapping
    translate: Translate
    translator: Translator
    freshrss: Freshrss
    rss: Rss
    emby: Emby
    fill_actor: FillActor
    model_config = SettingsConfigDict(toml_file='./config.toml')

    @classmethod
    def settings_customise_sources(cls, settings_cls: type[BaseSettings], **_: Any) -> tuple[BaseSettings, ...]:
        return (TomlConfigSettingsSource(settings_cls),)


config = Config()
