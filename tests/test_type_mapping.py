from replica_cygnus.models import SourceColumn
from replica_cygnus.type_mapping import postgres_type


def col(data_type, length=None, precision=None, scale=None):
    return SourceColumn(
        name="x",
        data_type=data_type,
        ordinal_position=1,
        is_nullable=True,
        character_maximum_length=length,
        numeric_precision=precision,
        numeric_scale=scale,
    )


def test_common_type_mapping():
    assert postgres_type(col("bigint")) == "bigint"
    assert postgres_type(col("character varying", length=50)) == "varchar(50)"
    assert postgres_type(col("numeric", precision=18, scale=2)) == "numeric(18,2)"
    assert postgres_type(col("timestamp without time zone")) == "timestamp without time zone"
    assert postgres_type(col("SUPER")) == "text"
