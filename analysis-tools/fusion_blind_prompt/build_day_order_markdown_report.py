#!/home/lachlan/miniconda3/envs/organoid/bin/python
from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path

from PIL import Image

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


def preview_png(source_tif: Path, dest_png: Path, max_width: int = 420) -> None:
    with Image.open(source_tif) as image:
        image = image.convert('RGB')
        if image.width > max_width:
            height = int(image.height * (max_width / image.width))
            image = image.resize((max_width, height))
        image.save(dest_png)


def main() -> int:
    parser = argparse.ArgumentParser(description='Build day-ordered markdown report from blind fusion analysis and internal mapping')
    parser.add_argument('analysis_json', type=Path)
    parser.add_argument('mapping_csv', type=Path)
    parser.add_argument('report_dir', type=Path)
    args = parser.parse_args()

    report_dir = args.report_dir
    assets_dir = report_dir / 'assets'
    report_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)

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

    lines = []
    lines.append('# Blind Fusion Cohort Report: Set 001')
    lines.append('')
    lines.append('This report orders the blinded UID images by their private source-date mapping and presents the refined fusion-analysis values with justification.')
    lines.append('')
    lines.append('Important: the prompt tool itself did not see the date or condition metadata; this ordering was reconstructed afterward from the private mapping file.')
    lines.append('')
    lines.append('## Cohort Summary')
    lines.append('')
    lines.append(f"- Images: `{len(dated)}`")
    lines.append(f"- Fusion ranking (strongest to weakest): `{', '.join(analysis['ranking_by_fusion_uid_desc'])}`")
    lines.append(f"- Review note: {analysis.get('review_note', '')}")
    lines.append(f"- Analysis note: {analysis.get('analysis_note', '')}")
    lines.append('')
    lines.append('## Day-Ordered Detail')
    lines.append('')

    for seq_idx, (uid, date_label, row, item) in enumerate(dated, start=1):
        rel = relative_offset(date_label, first_dt)
        src_tif = Path(row['source_path'])
        preview = assets_dir / f"{uid}.png"
        preview_png(src_tif, preview)
        lines.append(f"### Sequence Day {seq_idx}")
        lines.append('')
        lines.append(f"- UID: `{uid}`")
        lines.append(f"- Source date: `{date_label}`")
        lines.append(f"- Relative calendar offset from first source date: `{rel}` day(s)")
        lines.append(f"- Original source basename: `{row['source_basename']}`")
        lines.append(f"- Fusion ranking position: `{ranking_positions[uid]}`")
        lines.append(f"- Fusion score: `{item['fusion_score_0_to_5']}`")
        lines.append(f"- Fusion state: `{item['fusion_state_label']}`")
        lines.append(f"- Estimated organoid units: `{item['estimated_organoid_units']}`")
        lines.append(f"- Largest mass relative: `{item['largest_mass_relative_0_to_100']}`")
        lines.append(f"- Size relative: `{item['size_relative_0_to_100']}`")
        lines.append(f"- Perimeter complexity: `{item['perimeter_complexity_0_to_100']}`")
        lines.append(f"- Confidence: `{item['confidence_0_to_1']}`")
        if 'prior_consistency_note' in item:
            lines.append(f"- Prior consistency note: {item['prior_consistency_note']}")
        lines.append('')
        lines.append(f"![{uid}](assets/{preview.name})")
        lines.append('')
        lines.append('Justification:')
        lines.append(f"- Summary: {item['evidence']['summary_note']}")
        lines.append(f"- Relative position: {item['evidence']['relative_position_note']}")
        lines.append(f"- Texture/color: {item['evidence']['texture_color_note']}")
        lines.append(f"- Large connected mass present: `{item['evidence']['large_connected_mass_present']}`")
        lines.append(f"- Multiple separate round units present: `{item['evidence']['multiple_separate_round_units_present']}`")
        lines.append(f"- Visible boundaries between units: `{item['evidence']['visible_boundaries_between_units']}`")
        lines.append(f"- Irregular/thickened/collapsed regions present: `{item['evidence']['irregular_thickened_or_collapsed_regions_present']}`")
        lines.append('')

    (report_dir / 'set_001_day_order_report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({"report_dir": str(report_dir), "entries": len(dated)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
