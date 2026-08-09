import pytest

from replica_cygnus.errors import ConfigurationError
from replica_cygnus.models import TableConfig


def test_incremental_requires_key_and_watermark():
    with pytest.raises(ConfigurationError):
        TableConfig(source_schema="a", source_table="b", strategy="incremental")


def test_full_refresh_allows_no_key():
    cfg = TableConfig(source_schema="a", source_table="b", strategy="full_refresh")
    assert cfg.target_table == "b"
