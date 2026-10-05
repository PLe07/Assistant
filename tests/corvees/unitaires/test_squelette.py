import modules.corvees
from modules.corvees import cli


def test_le_module_existe():
    assert "corvées" in (modules.corvees.__doc__ or "")


def test_la_commande_repond(capsys):
    assert cli.main([]) == 0
    assert "corvées" in capsys.readouterr().out
