"""Export publication-friendly plots from the actual benchmark artifact."""
import json
import os
from pathlib import Path

os.environ.setdefault('MPLCONFIGDIR', str(Path(__file__).resolve().parents[1] / '.cache/matplotlib'))
os.environ.setdefault('XDG_CACHE_HOME', str(Path(__file__).resolve().parents[1] / '.cache'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def plot(directory):
    report = json.loads((directory / 'benchmark.json').read_text(encoding='utf-8'))
    names = list(report['runs'])
    metrics = [('Status accuracy', lambda r: r['status_accuracy']),
               ('Answer keyword accuracy', lambda r: r['answer_keyword_accuracy']),
               ('Evidence Hit@1', lambda r: r['hit_at_k']['1']),
               ('Abstention accuracy', lambda r: r['abstention_accuracy'])]
    fig, axes = plt.subplots(2, 2, figsize=(11, 7), constrained_layout=True)
    for ax, (title, getter) in zip(axes.flat, metrics):
        values = [getter(report['runs'][name]) for name in names]
        bars = ax.bar(names, [v or 0 for v in values], color=['#245b94', '#27886c', '#9463b2', '#bb7834'][:len(names)])
        ax.set(title=title, ylim=(0, 1.15), ylabel='Rate')
        ax.tick_params(axis='x', rotation=12)
        ax.bar_label(bars, labels=[f'{v:.1%}' if v is not None else 'N/A' for v in values], padding=3)
    fig.suptitle(f"RAG retrieval experiment | {next(iter(report['runs'].values()))['cases']} cases | fictional corpus")
    fig.savefig(directory / 'metrics.png', dpi=180)
    fig.savefig(directory / 'metrics.pdf')
    plt.close(fig)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path, nargs='?', default=Path('reports/latest'))
    plot(parser.parse_args().directory)
