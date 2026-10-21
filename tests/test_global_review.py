"""Casos de consolidación: nombres, configuración, referencia y sensibilidad controlada."""
import copy
import json
from pathlib import Path
import pandas as pd
from tp2.comparison import build_matrix, configuration_family
from tp2.global_review import operational_params, prepare_records
from tp2.storage import append_csv, write_json


def saved(root, identity, activity, image, variant, roi, params, features, roi_hash='same'):
    """Crea un registro de prueba confirmado y su fila de orden en el CSV de actividad."""
    record=dict(medicion_id=identity,actividad=activity,actividad_solicitada=activity,imagen_id=image,variante=variant,roi_id=roi,roi_hash=roi_hash,parametros=params,parametros_solicitados=params,caracteristicas=features,imagen_hash=image+variant)
    target=root/'mediciones'/identity;target.mkdir(parents=True)
    write_json(target/'medicion.json',record);(target/'GUARDADO').write_text('ok')
    append_csv(root/(activity+'.csv'),[dict(medicion_id=identity)])
    return record


def test_operational_parameters_ignore_inactive_detector_controls():
    """Cambiar FAST no crea una nueva configuración de Harris, pero sí de ORB."""
    a=dict(actividad='06_puntos',parametros=dict(method='Harris',harris_k=.04,orb_fast=20))
    b=copy.deepcopy(a);b['parametros']['orb_fast']=5
    assert configuration_family(a)==configuration_family(b)
    a['parametros']['method']=b['parametros']['method']='ORB'
    assert configuration_family(a)!=configuration_family(b)


def test_alias_uses_current_mask_and_preserves_original_records(tmp_path):
    """Un nombre anterior se unifica solo por hash exacto, sin escribir en el registro fuente."""
    from tp2.workflow import load_regions
    project=Path(__file__).resolve().parents[1]
    source=project/'rois/seleccion_final/regiones.json'
    payload=json.loads(source.read_text());payload['layers'][0]['features']['roi_id'][4]='region_macular'
    dest=tmp_path/'rois/seleccion_final';dest.mkdir(parents=True)
    write_json(dest/'regiones.json',payload)
    _,regions=load_regions(dest/'regiones.json')
    root=tmp_path/'resultados';root.mkdir()
    r=dict(roi_id='disco_optico',roi_hash=regions[4]['hash'],medicion_id='old')
    updated,aliases,_=prepare_records(root,[r])
    assert updated[0]['roi_id']=='region_macular' and len(aliases)==1
    assert r['roi_id']=='disco_optico'


def test_robustness_and_no_correlations_between_different_rois(tmp_path):
    """El resumen mide reducción de desvío; las correlaciones no mezclan regiones."""
    root=tmp_path/'resultados';root.mkdir()
    for roi,offset in [('vessel',0),('background',100)]:
        for i,(img,var,value) in enumerate([('Retina1_2','original',10),('Retina3','original',20),('Retina3','corregida',12),('Retina4','original',22),('Retina4','corregida',26)]):
            saved(root,roi+str(i),'01_intensidad',img,var,roi,{},dict(media=value+offset,varianza=(value+offset)**2))
    frame,_=build_matrix(root)
    summary=pd.read_csv(root/'08_resumen_robustez.csv')
    r=summary[(summary.imagen_id=='Retina3')&(summary.roi_id=='vessel')&(summary.caracteristica=='01_intensidad__media')].iloc[0]
    assert r.desvio_antes==10 and r.desvio_despues==2 and r.reduccion_relativa_desvio==.8
    assert r.resultado=='mas_cerca_de_referencia'
    corr=pd.read_csv(root/'08_correlaciones_spearman.csv')
    assert set(corr.roi_id)=={'vessel','background'} and set(corr.n)=={5}
    assert len(frame)==10


def test_sensitivity_separates_detector_methods_and_varies_one_parameter(tmp_path):
    """La sensibilidad compara SIFT consigo mismo; nunca combina Harris y ORB en un CV."""
    root=tmp_path/'resultados';root.mkdir()
    for i,(method,threshold,n) in enumerate([('SIFT',.04,7),('SIFT',.02,26),('ORB',20,4),('ORB',5,106),('Harris',.01,37)]):
        key='sift_contrast' if method=='SIFT' else 'orb_fast' if method=='ORB' else 'harris_threshold'
        saved(root,str(i),'06_puntos','Retina1_2','realzada','roi',dict(method=method,**{key:threshold}),dict(n_compatibles_posicion=n))
    build_matrix(root)
    sensitivity=pd.read_csv(root/'08_sensibilidad_configuraciones.csv')
    assert len(sensitivity)==2 and set(sensitivity.metodo)=={'SIFT','ORB'}


def test_roi_sensitivity_keeps_same_image_and_configuration(tmp_path):
    """La ROI auxiliar queda en la matriz completa y separada de las ROIs principales."""
    root=tmp_path/'resultados';root.mkdir();(tmp_path/'config').mkdir()
    config=dict(rois_principales=['roi'],sensibilidad_roi=dict(original='roi',modificada='expanded'))
    write_json(tmp_path/'config/analisis_global.json',config)
    params=dict(mode='count',bins=32,distances=[1],alpha=0,low=0,high=255)
    saved(root,'a','07_radiomica','Retina1_2','original','roi',params,dict(glcm_Contrast=2),roi_hash='original')
    saved(root,'b','07_radiomica','Retina1_2','original','expanded',params,dict(glcm_Contrast=3),roi_hash='expanded')
    full,_=build_matrix(root)
    compact=pd.read_csv(root/'08_matriz_representativa.csv')
    sensitivity=pd.read_csv(root/'08_sensibilidad_roi.csv')
    assert len(full)==2 and len(compact)==1 and len(sensitivity)==1
    assert sensitivity.iloc[0].cambio_relativo==.5
