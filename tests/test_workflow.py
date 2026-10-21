"""Verificaciones del flujo por lotes: identidad de ROIs, revisión y reanudación."""
from pathlib import Path
import copy
import json
import numpy as np
from tp2 import workflow as wf
from tp2.storage import read_records
from tp2.engine import replay
from tp2.comparison import build_matrix

PROJECT=Path(__file__).resolve().parents[1]
REGIONS=PROJECT/'rois/seleccion_final/regiones.json'


def test_user_regions_and_snapshots():
    """Las ROIs originales conservan sus máscaras y coordenadas."""
    payload,regions=wf.load_regions(REGIONS)
    records=read_records(PROJECT/'resultados')
    # Las copias añadidas para sensibilidad y los cambios de nombre son válidos.
    original_hashes={r['roi_hash'] for r in records if 'firma_lote' not in r}
    for region in regions:
        if region['hash'] not in original_hashes:
            continue
        matches=[r for r in records if r['roi_hash']==region['hash'] and 'firma_lote' not in r]
        assert len(matches)==13
        assert {r['roi_hash'] for r in matches}=={region['hash']}
        for r in matches:
            assert r['roi_geometria']==region['geometry']


def test_configuration_expansion():
    """LBP empareja P y R y conserva detectores/anchos como configuraciones separadas."""
    configs=wf.configurations('04_lbp',copy.deepcopy(wf.DEFAULTS['04_lbp']))
    assert [(p['points'],p['radius']) for p in configs]==[(8,1),(16,2),(24,3)]
    assert [p['method'] for p in wf.configurations('06_puntos',copy.deepcopy(wf.DEFAULTS['06_puntos']))]==['Harris','SIFT','ORB']
    assert len(wf.configurations('07_radiomica',copy.deepcopy(wf.DEFAULTS['07_radiomica'])))==3


def test_batch_background_replay_and_resume(tmp_path):
    """Un lote guarda nombres correctos, resta el fondo elegido y omite repeticiones exactas."""
    settings=copy.deepcopy(wf.DEFAULTS);options=dict(correct_background=True,skip_existing=True)
    names=['Retina1_referencia']
    tasks,pool=wf.prepare_tasks(PROJECT,REGIONS,['01_intensidad'],names,['vaso_grueso','fondo'],settings,options)
    results=wf.execute_batch(PROJECT,tmp_path,REGIONS,tasks,pool)
    assert [r['estado'] for r in results]==['guardada','guardada']
    records=read_records(tmp_path);v=next(r for r in records if r['roi_id']=='vaso_grueso');bg=next(r for r in records if r['roi_id']=='fondo')
    f=v['caracteristicas'];assert np.isclose(f['media_fondo'],bg['caracteristicas']['media'])
    assert np.isclose(f['intensidad_integrada_corregida'],f['intensidad_integrada']-f['n_pixeles']*f['media_fondo'])
    repeated=replay(v,tmp_path);assert np.isclose(repeated['features']['media_fondo'],f['media_fondo'])
    assert all(r['estado']=='omitida' for r in wf.execute_batch(PROJECT,tmp_path,REGIONS,tasks,pool))
    assert len(read_records(tmp_path))==2


def test_segmentation_requires_review(tmp_path):
    """Forma no usa una máscara automática hasta su aprobación explícita y conserva ediciones."""
    settings=copy.deepcopy(wf.DEFAULTS);options=dict(skip_existing=True)
    tasks,pool=wf.prepare_tasks(PROJECT,REGIONS,['00_segmentacion','02_geometria'],['Retina1_referencia'],['vaso_grueso'],settings,options)
    results=wf.execute_batch(PROJECT,tmp_path,REGIONS,tasks,pool)
    assert [r['estado'] for r in results]==['guardada','error']
    _,regions=wf.load_regions(REGIONS);region=next(r for r in regions if r['id']=='vaso_grueso');image,meta=pool['Retina1_referencia']
    before=wf.read_segmentation(tmp_path,meta,region);assert not before['aprobada']
    wf.approve_segmentation(tmp_path,image,meta,region)
    results=wf.execute_batch(PROJECT,tmp_path,REGIONS,tasks,pool)
    assert [r['estado'] for r in results]==['omitida','guardada']
    assert wf.read_segmentation(tmp_path,meta,region)['aprobada']


def test_global_keeps_all_configurations(tmp_path):
    """La matriz conserva las tres escalas LBP, sin sobrescribirlas con la última."""
    settings=copy.deepcopy(wf.DEFAULTS)
    tasks,pool=wf.prepare_tasks(PROJECT,REGIONS,['04_lbp'],['Retina1_referencia'],['fondo'],settings,dict(skip_existing=True))
    reports=wf.execute_batch(PROJECT,tmp_path,REGIONS,tasks,pool)
    assert all(r['estado']=='guardada' for r in reports)
    matrix,_=build_matrix(tmp_path)
    identities=[c for c in matrix if c.endswith('__medicion_id')]
    assert len(identities)==3
    assert len(matrix)==1
