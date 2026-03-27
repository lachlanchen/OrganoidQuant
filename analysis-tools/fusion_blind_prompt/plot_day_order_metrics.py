#!/home/lachlan/miniconda3/envs/organoid/bin/python
from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

DATE_RE = re.compile(r"(?P<day>\d{2})-十二月-2025")


def parse_rows(mapping_csv: Path):
    with mapping_csv.open('r', encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise RuntimeError('empty mapping csv')
    return rows


def extract_date_label(source_folder: str) -> str:
    return Path(source_folder).name


def relative_offset(date_label: str, first_dt: datetime) -> int:
    m = DATE_RE.search(date_label)
    if not m:
        raise ValueError(f'Could not parse date from {date_label}')
    dt = datetime.strptime(f"2025-12-{m.group('day')}", '%Y-%m-%d')
    return (dt - first_dt).days


def main() -> int:
    parser = argparse.ArgumentParser(description='Plot day-ordered metrics for a blinded fusion cohort')
    parser.add_argument('analysis_json', type=Path)
    parser.add_argument('mapping_csv', type=Path)
    parser.add_argument('output_dir', type=Path)
    args = parser.parse_args()

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    analysis = json.loads(args.analysis_json.read_text(encoding='utf-8'))
    rows = parse_rows(args.mapping_csv)
    row_by_uid = {row['uid']: row for row in rows}
    image_by_uid = {item['uid']: item for item in analysis['images']}

    dated = []
    for uid in analysis['uids_in_order']:
        row = row_by_uid[uid]
        date_label = extract_date_label(row['source_folder'])
        dated.append((uid, date_label, row, image_by_uid[uid]))

    dated.sort(key=lambda item: item[1])
    first_match = DATE_RE.search(dated[0][1])
    if not first_match:
        raise ValueError('Could not parse first date label')
    first_dt = datetime.strptime(f"2025-12-{first_match.group('day')}", '%Y-%m-%d')

    ranking_positions = {uid: idx + 1 for idx, uid in enumerate(analysis['ranking_by_fusion_uid_desc'])}

    table_rows = []
    for seq_idx, (uid, date_label, row, item) in enumerate(dated, start=1):
        table_rows.append({
            'sequence_day': seq_idx,
            'source_date': date_label,
            'relative_offset_days': relative_offset(date_label, first_dt),
            'uid': uid,
            'source_basename': row['source_basename'],
            'fusion_rank': ranking_positions[uid],
            'fusion_score_0_to_5': item['fusion_score_0_to_5'],
            'fusion_state_label': item['fusion_state_label'],
            'estimated_organoid_units': item['estimated_organoid_units'],
            'largest_mass_relative_0_to_100': item['largest_mass_relative_0_to_100'],
            'size_relative_0_to_100': item['size_relative_0_to_100'],
            'perimeter_complexity_0_to_100': item['perimeter_complexity_0_to_100'],
            'confidence_0_to_1': item['confidence_0_to_1'],
        })

    csv_path = output_dir / 'set_001_metric_table.csv'
    with csv_path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(table_rows[0].keys()))
        writer.writeheader()
        writer.writerows(table_rows)

    x = [row['sequence_day'] for row in table_rows]
    date_labels = [f"D{row['sequence_day']}\n{row['source_date'][:2]}" for row in table_rows]

    metrics = [
        ('fusion_score_0_to_5', 'Fusion Score (0-5)', (0, 5)),
        ('estimated_organoid_units', 'Estimated Organoid Units', None),
        ('largest_mass_relative_0_to_100', 'Largest Mass Relative (%)', (0, 100)),
        ('size_relative_0_to_100', 'Size Relative (%)', (0, 100)),
        ('perimeter_complexity_0_to_100', 'Perimeter Complexity (%)', (0, 100)),
        ('confidence_0_to_1', 'Confidence (0-1)', (0, 1)),
    ]

    colors = ['#B11E35', '#2C6E49', '#1D4E89', '#D17B0F', '#6A4C93', '#4C4C4C']
    fig, axes = plt.subplots(3, 2, figsize=(14, 12), constrained_layout=True)
    axes = axes.ravel()

    for ax, (metric_key, title, ylim), color in zip(axes, metrics, colors):
        y = [row[metric_key] for row in table_rows]
        ax.plot(x, y, color=color, marker='o', linewidth=2.2, markersize=6)
        for xi, yi, row in zip(x, y, table_rows):
            ax.annotate(row['uid'].replace('uid_', '')[:6], (xi, yi), textcoords='offset points', xytext=(0, 8), ha='center', fontsize=8, color=color)
        ax.set_title(title, fontsize=12, fontweight='bold')
        ax.set_xticks(x, date_labels)
        ax.grid(True, alpha=0.25)
        if ylim is not None:
            ax.set_ylim(*ylim)
        ax.set_xlabel('Blind Sequence Day')

    fig.suptitle('Set 001 Blind Fusion Quantification Summary', fontsize=16, fontweight='bold')
    png_path = output_dir / 'set_001_metric_summary.png'
    pdf_path = output_dir / 'set_001_metric_summary.pdf'
    fig.savefig(png_path, dpi=220, bbox_inches='tight')
    fig.savefig(pdf_path, bbox_inches='tight')
    plt.close(fig)

    print(json.dumps({
        'csv': str(csv_path),
        'png': str(png_path),
        'pdf': str(pdf_path),
        'rows': len(table_rows),
    }))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
