"""Selección representativa y comparaciones controladas de resultados ya calculados."""

import copy
import json
from itertools import combinations
from pathlib import Path
import numpy as np
import pandas as pd
from .storage import write_json


FEATURES = {
    '01_intensidad': ['media','mediana','desviacion','varianza','iqr','media_corregida_fondo'],
    '02_geometria': ['area_px2','perimetro_px','circularidad','excentricidad','solidity','feret_max_px'],
    '03_estructura': ['longitud_esqueleto_px','n_extremos','n_bifurcaciones','n_ramas','espesor_local_medio_px','tortuosidad_media'],
    '04_lbp': ['lbp_entropia','lbp_uniformidad'],
    '04_gabor': ['gabor_l4_a0_energia','gabor_l8_a0_energia','gabor_l16_a0_energia'],
    '04_wavelet': ['wavelet_H1_energia','wavelet_V1_energia','wavelet_D1_energia','wavelet_H2_energia'],
    '05_multiescala': ['LoG_s1_abs_media','LoG_s2_abs_media','LoG_s4_abs_media','LoG_s8_abs_media'],
    '06_puntos': ['n_puntos_a','n_puntos_b','n_correspondencias','n_compatibles_posicion','fraccion_compatibles'],
    '07_radiomica': ['glcm_Contrast','glcm_JointEntropy','glcm_Idm','glrlm_ShortRunEmphasis','glrlm_LongRunEmphasis','glszm_SmallAreaEmphasis','glszm_ZoneEntropy','gldm_DependenceEntropy','ngtdm_Coarseness','ngtdm_Strength'],
}


def operational_params(record):
    """Conserva parámetros activos: un detector no depende de controles de otros métodos."""
    p=copy.deepcopy(record.get('parametros_solicitados',record['parametros']))
    if record['actividad']=='06_puntos':
        common=['method','max_points','low','high','ratio','mutual','tolerance']
        specific={'Harris':['harris_k','harris_threshold','min_distance','harris_block','harris_size','subpixel'],
                  'SIFT':['sift_contrast','sift_edge','sift_sigma'],
                  'ORB':['orb_scale','orb_levels','orb_fast','orb_patch']}
        return {k:p[k] for k in common+specific[p['method']] if k in p}
    if record['actividad']=='07_radiomica':
        return {k:p[k] for k in ['mode','low','high','distances','alpha','bins' if p['mode']=='count' else 'width'] if k in p}
    return p


def prepare_records(root, records):
    """Usa nombres actuales solo si el hash coincide de modo unívoco; preserva los registros originales."""
    records=copy.deepcopy(records);aliases=[]
    path=Path(root).parent/'rois/seleccion_final/regiones.json'
    if path.exists():
        from .workflow import load_regions
        _,regions=load_regions(path)
        names={r['id'] for r in regions};by_hash={}
        for r in regions:by_hash.setdefault(r['hash'],[]).append(r['id'])
        for r in records:
            candidates=by_hash.get(r['roi_hash'],[])
            if r['roi_id'] not in names and len(candidates)==1:
                aliases.append(dict(medicion_id=r['medicion_id'],nombre_guardado=r['roi_id'],nombre_actual=candidates[0],roi_hash=r['roi_hash']))
                r['roi_id']=candidates[0]
    path=Path(root).parent/'config/analisis_global.json'
    config=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    return records,aliases,config


def save_table(root,name,rows,columns):
    """Exporta tablas con encabezados incluso cuando no hay pares comparables."""
    pd.DataFrame(rows,columns=columns).to_csv(Path(root)/name,index=False,encoding='utf-8-sig')


def equal_context(a,b):
    """Verifica ROI, receta de segmentación y selección de fondo al comparar versiones."""
    def recipe(r):
        """Extrae los parámetros de segmentación, excluyendo la máscara resultante."""
        s=r.get('segmentacion',{})
        return s.get('parametros',s.get('params',{}))
    return a['roi_hash']==b['roi_hash'] and recipe(a)==recipe(b) and a.get('fondo_snapshot')==b.get('fondo_snapshot') and a.get('actividad_solicitada')==b.get('actividad_solicitada')


def export_review(root, records, order, config, family_function):
    """Selecciona features, compara referencia y ROI, y separa sensibilidad de cada parámetro."""
    latest={}
    for r in sorted(records,key=lambda r:order.get(r['medicion_id'],-1)):
        latest[(r['imagen_id'],r['variante'],r['roi_id'],family_function(r))]=r
    records=list(latest.values());chosen={};rows={};evidence=[]
    for r in sorted(records,key=lambda r:order.get(r['medicion_id'],-1)):
        activity=r['actividad'];p=operational_params(r)
        if config.get('rois_principales') and r['roi_id'] not in config['rois_principales']:continue
        wanted=config.get('configuraciones_representativas',{}).get(activity,{})
        if any(p.get(k)!=v for k,v in wanted.items()):continue
        if activity=='06_puntos' and any(r.get(k)!=v for k,v in config.get('comparacion_puntos',{}).items()):continue
        family=activity+'['+p['method']+']' if activity=='06_puntos' else activity
        chosen[(r['imagen_id'],r['variante'],r['roi_id'],family)]=r
    for (img,var,roi,family),r in chosen.items():
        row=rows.setdefault((img,var,roi),dict(imagen_id=img,variante=var,roi_id=roi))
        for name in FEATURES.get(r['actividad'],[]):
            if name in r['caracteristicas']:row[family+'__'+name]=r['caracteristicas'][name]
        evidence.append(dict(imagen_id=img,variante=var,roi_id=roi,familia=family,medicion_id=r['medicion_id'],parametros=operational_params(r),roi_hash=r['roi_hash']))
    compact=pd.DataFrame(rows.values()).sort_values(['roi_id','imagen_id','variante'])
    compact.to_csv(Path(root)/'08_matriz_representativa.csv',index=False,encoding='utf-8-sig')
    write_json(Path(root)/'08_protocolo_comparacion.json',dict(configuracion=config,seleccion=evidence,criterios=['Comparaciones descriptivas: una misma retina y sus versiones, sin significación estadística.','Cercanía a la referencia no demuestra exactitud anatómica de una segmentación.','Vacíos: característica no calculada o indefinida; no sustituir por cero.','Correlaciones dentro de cada ROI, con al menos cinco versiones y características variables.']))
    robustness=[]
    for (img,var,roi,family),b in chosen.items():
        if var not in ('corregida','realzada','intermedia'):continue
        a=chosen.get((img,'original',roi,family));ref=chosen.get(('Retina1_2','original',roi,family))
        if a is None or ref is None:continue
        controlled=operational_params(a)==operational_params(b)==operational_params(ref) and equal_context(a,b) and equal_context(a,ref)
        for name in FEATURES.get(b['actividad'],[]):
            values=[r['caracteristicas'].get(name) for r in [ref,a,b]]
            if any(v is None for v in values) or not np.isfinite(values).all():continue
            v,x,y=values;e0,e1=abs(x-v),abs(y-v)
            status='desvio_sin_cambio' if np.isclose(e0,e1,rtol=1e-6,atol=1e-9) else 'mas_cerca_de_referencia' if e1<e0 else 'mas_lejos_de_referencia'
            robustness.append(dict(imagen_id=img,variante=var,roi_id=roi,caracteristica=family+'__'+name,referencia=v,antes=x,despues=y,desvio_antes=e0,desvio_despues=e1,reduccion_desvio=e0-e1,reduccion_relativa_desvio=(e0-e1)/e0 if e0>1e-12 else np.nan,comparacion_controlada=controlled,resultado=status if controlled else 'revisar_contexto'))
    save_table(root,'08_resumen_robustez.csv',robustness,['imagen_id','variante','roi_id','caracteristica','referencia','antes','despues','desvio_antes','desvio_despues','reduccion_desvio','reduccion_relativa_desvio','comparacion_controlada','resultado'])
    sensitivity=[];groups={}
    for r in records:
        method=operational_params(r).get('method','') if r['actividad']=='06_puntos' else ''
        key=(r['imagen_id'],r['variante'],r['roi_id'],r['actividad'],method,r['roi_hash'])
        groups.setdefault(key,[]).append(r)
    for key,group in groups.items():
        for a,b in combinations(group,2):
            pa,pb=operational_params(a),operational_params(b)
            diff=[k for k in pa.keys()|pb.keys() if pa.get(k)!=pb.get(k)]
            if not diff or (len(diff)>1 and set(diff)!={'points','radius'}):continue
            for name in a['caracteristicas'].keys()&b['caracteristicas'].keys():
                x,y=a['caracteristicas'][name],b['caracteristicas'][name]
                if x is None or y is None or not np.isfinite([x,y]).all():continue
                sensitivity.append(dict(imagen_id=key[0],variante=key[1],roi_id=key[2],actividad=key[3],metodo=key[4],parametros_modificados=','.join(sorted(diff)),medicion_a=a['medicion_id'],medicion_b=b['medicion_id'],parametros_a=json.dumps(pa,sort_keys=True),parametros_b=json.dumps(pb,sort_keys=True),caracteristica=name,valor_a=x,valor_b=y,diferencia=y-x,cambio_relativo=(y-x)/abs(x) if abs(x)>1e-12 else np.nan))
    save_table(root,'08_sensibilidad_configuraciones.csv',sensitivity,['imagen_id','variante','roi_id','actividad','metodo','parametros_modificados','medicion_a','medicion_b','parametros_a','parametros_b','caracteristica','valor_a','valor_b','diferencia','cambio_relativo'])
    pair=config.get('sensibilidad_roi',{});roi_rows=[]
    if pair:
        bases={(r['imagen_id'],r['variante'],family_function(r)):r for r in records if r['roi_id']==pair['original']}
        for b in records:
            if b['roi_id']!=pair['modificada']:continue
            a=bases.get((b['imagen_id'],b['variante'],family_function(b)))
            if a is None or a.get('imagen_hash')!=b.get('imagen_hash'):continue
            for name in a['caracteristicas'].keys()&b['caracteristicas'].keys():
                x,y=a['caracteristicas'][name],b['caracteristicas'][name]
                if x is None or y is None or not np.isfinite([x,y]).all():continue
                roi_rows.append(dict(imagen_id=a['imagen_id'],variante=a['variante'],roi_original=a['roi_id'],roi_modificada=b['roi_id'],medicion_original=a['medicion_id'],medicion_modificada=b['medicion_id'],caracteristica=name,valor_original=x,valor_modificada=y,diferencia=y-x,cambio_relativo=(y-x)/abs(x) if abs(x)>1e-12 else np.nan))
    save_table(root,'08_sensibilidad_roi.csv',roi_rows,['imagen_id','variante','roi_original','roi_modificada','medicion_original','medicion_modificada','caracteristica','valor_original','valor_modificada','diferencia','cambio_relativo'])
    correlations=[]
    for roi,part in compact.groupby('roi_id'):
        data=part.drop(columns=['imagen_id','variante','roi_id']).apply(pd.to_numeric,errors='coerce')
        eligible=[c for c in data if data[c].notna().sum()>=5 and data[c].nunique()>1]
        corr=data[eligible].corr(method='spearman',min_periods=5)
        for a,b in combinations(eligible,2):
            rho=corr.at[a,b];n=int(data[[a,b]].dropna().shape[0])
            if np.isfinite(rho):correlations.append(dict(roi_id=roi,feature_a=a,feature_b=b,n=n,rho=float(rho)))
    save_table(root,'08_correlaciones_spearman.csv',correlations,['roi_id','feature_a','feature_b','n','rho'])
    save_table(root,'08_posible_redundancia.csv',[r for r in correlations if abs(r['rho'])>=.95],['roi_id','feature_a','feature_b','n','rho'])
    coverage=[]
    for key in sorted({(r['imagen_id'],r['variante'],r['roi_id']) for r in records}):
        group=[r for r in records if (r['imagen_id'],r['variante'],r['roi_id'])==key]
        coverage.append(dict(imagen_id=key[0],variante=key[1],roi_id=key[2],actividades=','.join(sorted({r['actividad'] for r in group})),n_configuraciones=len(group),roi_hashes=','.join(sorted({r['roi_hash'] for r in group}))))
    save_table(root,'08_cobertura.csv',coverage,['imagen_id','variante','roi_id','actividades','n_configuraciones','roi_hashes'])
    return compact
