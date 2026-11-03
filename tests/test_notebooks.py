"""Execute every example notebook (from the cache; no API key). Equivalent: pytest --nbmake examples/"""

from pathlib import Path

import pytest

nbformat = pytest.importorskip("nbformat")
nbclient = pytest.importorskip("nbclient")
pytest.importorskip("sentence_transformers")

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.ipynb")), ids=lambda p: p.stem)
def test_notebook_runs(path):
    nb = nbformat.read(path, as_version=4)
    nbclient.NotebookClient(nb, timeout=1200, kernel_name="python3", resources={"metadata": {"path": str(EXAMPLES)}}).execute()
