"""Dump Zac's notebook (source, printed output and displayed tables) to plain text.

Usage: python3 -I verification/dump_notebook.py data/raw/IPA_Service_Ticket_SQL_Analysis.ipynb data/derived/notebook_dump.md
"""
import html
import json
import re
import sys


def table_text(markup):
    markup = re.sub(r'<style.*?</style>', '', markup, flags=re.S)
    lines = []
    summary = re.search(r'<summary[^>]*>(.*?)</summary>', markup, flags=re.S)
    if summary:
        lines.append('[' + re.sub(r'<[^>]+>', '', summary.group(1)) + ']')
    rows = re.findall(r'<tr.*?</tr>', markup, flags=re.S)
    for row in rows:
        cells = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', row, flags=re.S)
        lines.append('| ' + ' | '.join(html.unescape(re.sub(r'<[^>]+>', '', x)).strip() for x in cells) + ' |')
    if not rows:
        lines.append(html.unescape(re.sub(r'<[^>]+>', '', markup)).strip())
    return '\n'.join(lines)


def main(source, target):
    notebook = json.load(open(source))
    out = []
    for i, cell in enumerate(notebook['cells']):
        out.append(f'\n## Cell {i} [{cell["cell_type"]}]\n')
        body = ''.join(cell['source'])
        out.append(body if cell['cell_type'] == 'markdown' else '```python\n' + body + '\n```')
        for output in cell.get('outputs', []):
            if 'text' in output:
                out.append('Output:\n```\n' + ''.join(output['text']).rstrip() + '\n```')
            elif 'data' in output:
                data = output['data']
                if 'text/html' in data:
                    out.append('Displayed table:\n' + table_text(''.join(data['text/html'])))
                elif 'text/markdown' in data:
                    out.append('Displayed markdown:\n' + ''.join(data['text/markdown']))
                elif 'image/png' in data:
                    out.append('[chart image]')
                elif 'text/plain' in data:
                    out.append('Value: ' + ''.join(data['text/plain']))
    open(target, 'w').write('\n'.join(out) + '\n')


if __name__ == '__main__':
    main(*sys.argv[1:3])
