import pytest

from replica_cygnus.errors import ConfigurationError
from replica_cygnus.identifiers import qualified_redshift, validate_identifier


def test_valid_identifier():
    assert validate_identifier("clientes_proyectos") == "clientes_proyectos"
    assert qualified_redshift("grupocygnus", "clientes") == '"grupocygnus"."clientes"'


@pytest.mark.parametrize("value", ["clientes;drop", "con espacio", "1tabla", "", "a.b"])
def test_invalid_identifier(value):
    with pytest.raises(ConfigurationError):
        validate_identifier(value)
