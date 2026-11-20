"""Execute the notebook headless with injected parameters when papermill is not installed (nbclient only).

Parameters are injected the way papermill does it: a new cell right after the cell tagged 'parameters', holding
literal assignments, so values edited in the notebook are overridden and nothing else changes.
"""
from pathlib import Path


def execute(notebook, out_path, params, cwd=None, kernel_name='python3', timeout=3600):
    import nbformat
    from nbclient import NotebookClient
    nb = nbformat.read(str(notebook), as_version=4)
    idx = next((i for i, c in enumerate(nb.cells) if 'parameters' in c.get('metadata', {}).get('tags', [])), None)
    if idx is None:
        raise ValueError('the notebook has no cell tagged "parameters"')
    src = '# Injected parameters\n' + '\n'.join(f'{k} = {v!r}' for k, v in params.items())
    cell = nbformat.v4.new_code_cell(src)
    cell.metadata['tags'] = ['injected-parameters']
    nb.cells.insert(idx + 1, cell)
    client = NotebookClient(nb, timeout=timeout, kernel_name=kernel_name,
                            resources={'metadata': {'path': str(cwd or Path(notebook).parent)}})
    try:
        client.execute()
    finally:
        nbformat.write(nb, str(out_path))
    return out_path
