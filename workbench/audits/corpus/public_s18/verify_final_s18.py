SKIP_TOKENS = ('S' + '132', 'S' + '312', '22014' + '23119', 'abo' + '2236')
"""Recompute human 3D corpus scope counts from the portable curve table."""
from collections import defaultdict
from pathlib import Path
import csv
import gzip
import hashlib
import io
import json

HERE = Path(__file__).resolve().parent
QUALIFIED_ORIGINS = {
    'direct_patient_PDO', 'PDX_derived_organoid', 'ipsc_or_normal_organoid',
    'pluripotent_stem_cell_organoid', 'adult_stem_cell_organoid',
    'primary_human_donor_chip', 'primary_human_patient_chip',
}


def checked(name):
    p = HERE / name
    assert not any(t.casefold() in str(p.resolve()).casefold() for t in SKIP_TOKENS)
    return p


def load(name):
    return json.loads(checked(name).read_text())


def check():
    hashes = load('SHA256SUMS.json')
    for name, expected in hashes.items():
        assert hashlib.sha256(checked(name).read_bytes()).hexdigest() == expected, name
    summary = load('b_axis_public_summary.json')
    studies = load('study_summary_public.json')
    totals = {(scope, k): {'curves': 0, 'measurement_points': 0, 'study_ids': set(), 'donors': set()}
              for scope in ('strict_direct_patient', 'all_qualified_human_3d') for k in (5, 6)}
    by_study = defaultdict(lambda: dict(ge5_curves=0, observations=0, strict_ge5_curves=0, origin=set(), system=set()))
    curve_ids = set()
    points = 0
    with gzip.open(checked('curves_master_public.csv.gz'), 'rt', newline='') as stream:
        for row in csv.DictReader(stream):
            assert not any(t.casefold() in str(row).casefold() for t in SKIP_TOKENS)
            assert row['curve_id'] not in curve_ids
            curve_ids.add(row['curve_id'])
            nd, n = int(row['positive_doses']), int(row['points'])
            assert nd >= 0 and n >= nd
            points += n
            assert row['qualified_human_3d'] in ('0', '1') and row['is_direct_patient'] in ('0', '1')
            qualified = row['qualified_human_3d'] == '1'
            assert not qualified or (row['origin'] in QUALIFIED_ORIGINS and row['system'] in ('3D_organoid', 'chip'))
            strict = qualified and row['is_direct_patient'] == '1' and row['origin'] == 'direct_patient_PDO'
            for scope, eligible in (('strict_direct_patient', strict), ('all_qualified_human_3d', qualified)):
                for k in (5, 6):
                    if eligible and nd >= k:
                        cell = totals[scope, k]
                        cell['curves'] += 1
                        cell['measurement_points'] += n
                        cell['study_ids'].add(row['study'])
                        if row['deduplicated_donor_group']:
                            cell['donors'].add(row['deduplicated_donor_group'])
            if qualified and nd >= 5:
                cell = by_study[row['study']]
                cell['ge5_curves'] += 1
                cell['observations'] += n
                cell['strict_ge5_curves'] += int(strict)
                cell['origin'].add(row['origin'])
                cell['system'].add(row['system'])
    assert len(curve_ids) == summary['master_curves'] == 13780
    assert points == summary['master_observations'] == 208824
    expected_cells = {
        ('strict_direct_patient', 5): (34, 13444, 202498),
        ('strict_direct_patient', 6): (29, 12908, 197293),
        ('all_qualified_human_3d', 5): (40, 13585, 206113),
        ('all_qualified_human_3d', 6): (35, 13003, 200084),
    }
    actual = {}
    for (scope, k), cell in totals.items():
        expected = summary['scopes'][scope][str(k)]
        result = dict(studies=len(cell['study_ids']), curves=cell['curves'], measurement_points=cell['measurement_points'],
                      study_ids=sorted(cell['study_ids']), resolved_deduplicated_donor_groups=len(cell['donors']))
        for key, value in result.items():
            assert value == expected[key], (scope, k, key, value, expected[key])
        assert (result['studies'], result['curves'], result['measurement_points']) == expected_cells[scope, k]
        actual[f'{scope}_ge{k}'] = result
    assert len(studies) == len(by_study) == 40
    assert {s['doi'] for s in studies} == set(by_study)
    for study in studies:
        for key, value in by_study[study['doi']].items():
            assert study[key] == (sorted(value) if isinstance(value, set) else value), (study['doi'], key)
    calibration = summary['PDF_blinded_digitization_error_band']
    assert calibration['curves'] == 26 and calibration['paired_points'] == 154
    return dict(status='passed', master_curves=len(curve_ids), master_observations=points,
                qualified_study_rows=len(studies), scopes=actual, sha256_files_verified=len(hashes),
                calibration_summary=calibration)


if __name__ == '__main__':
    print(json.dumps(check(), ensure_ascii=False))
