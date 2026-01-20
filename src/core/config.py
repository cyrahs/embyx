import os
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict, TomlConfigSettingsSource


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


class Freshrss(BaseModel):
    freshrss_url: str
    freshrss_api_key: str
    proxy: str


class Emby(BaseModel):
    url: str
    api_key: str
    user_id: str


class FillActor(BaseModel):
    actor_brand_path: Path
    additional_brand_path: list[Path]
    move_in_path: Path


class CloudDrive(BaseModel):
    address: str
    api_token: str
    task_dir_path: str
    cloud_name: str
    cloud_account_id: str


class Config(BaseSettings):
    log_dir: Path
    avid: Avid
    archive: Archive
    mapping: Mapping
    translate: Translate
    translator: Translator
    clouddrive: CloudDrive
    freshrss: Freshrss
    emby: Emby
    fill_actor: FillActor
    model_config = SettingsConfigDict(
        toml_file='./config.toml',
        env_file='.env',
        env_nested_delimiter='__',
        case_sensitive=False,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        **_: Any,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            env_settings,
            dotenv_settings,
            TomlConfigSettingsSource(settings_cls),
        )

def _use_test_config() -> bool:
    if os.environ.get('EMBYX_USE_REAL_CONFIG'):
        return False
    return 'pytest' in sys.modules or os.environ.get('PYTEST_CURRENT_TEST') is not None


def _build_test_config() -> Config:
    return Config.model_construct(
        log_dir=Path('log'),
        avid=Avid(get_id_exceptions=[], ignored_id_pattern=[], brand_mapping={}),
        archive=Archive(mapping={}, min_size=0, src_dir=Path(), dst_dir=Path(), brand_mapping={}),
        mapping=Mapping(src_dir=Path(), dst_dir=Path()),
        translate=Translate(nfo_dir=Path()),
        translator=Translator(openai_api_key='', openai_base_url='http://localhost', model_list=[]),
        clouddrive=CloudDrive(
            address='localhost:0',
            api_token='',
            task_dir_path='',
            cloud_name='',
            cloud_account_id='',
        ),
        freshrss=Freshrss(freshrss_url='', freshrss_api_key='', proxy=''),
        emby=Emby(url='', api_key='', user_id=''),
        fill_actor=FillActor(actor_brand_path=Path(), additional_brand_path=[], move_in_path=Path()),
    )


config = _build_test_config() if _use_test_config() else Config()
