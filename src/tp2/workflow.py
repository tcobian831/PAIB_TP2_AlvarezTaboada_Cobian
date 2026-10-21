"""ROIs persistentes, trabajos por lotes y revisión de segmentaciones de cada imagen."""

from pathlib import Path
from itertools import product
import csv
import json
import hashlib
import copy
import traceback
import numpy as np
import tifffile
from napari.layers import Shapes
from .data import array_hash, load_pool
from .engine import run
from .structure import segment_vessels
from .storage import write_json, save_measurement, read_records
from .figures import measurement_figure

ACTIVITIES = {
    '01_intensidad': '1 · Intensidad y corrección por fondo',
    '00_segmentacion': '2–3 · Preparar máscaras vasculares',
    '02_geometria': '2 · Forma de vasos segmentados',
    '02_forma_roi': '2 · Forma del contorno de una ROI',
    '03_estructura': '3 · Esqueleto y estructura vascular',
    '04_lbp': '4 · LBP e histogramas',
    '04_gabor': '4 · Banco de Gabor',
    '04_wavelet': '4 · Wavelet',
    '05_multiescala': '5 · Gaussianas, LoG y DoG',
    '06_puntos': '6 · Harris, SIFT, ORB y correspondencias',
    '07_radiomica': '7 · Radiómica',
}
DEFAULTS = {
    '01_intensidad': {'percentiles': [1,5,10,25,50,75,90,95,99]},
    '00_segmentacion': {'sigmas': [1,2,3], 'threshold': None, 'min_size': 20, 'closing': 0, 'fill_holes': 0},
    '02_geometria': {}, '02_forma_roi': {},
    '03_estructura': {'prune_lengths': [0], 'calculate_thickness': True},
    '04_lbp': {'pairs': '8:1;16:2;24:3', 'method': 'uniform'},
    '04_gabor': {'wavelengths': [4,8,16], 'angles': [0,45,90,135], 'sigma_ratio': .56, 'gamma': .5},
    '04_wavelet': {'wavelet': 'db2', 'levels': [2,3]},
    '05_multiescala': {'sigmas': [1,2,4,8], 'dog_k': 2**(1/3)},
    '06_puntos': {'methods': ['Harris','SIFT','ORB'], 'pair_mode': 'original_procesada',
        'max_points': 500, 'ratio': .75, 'mutual': True, 'tolerance': 3, 'low': 0, 'high': 255,
        'harris_k': .04, 'harris_threshold': .01, 'min_distance': 5, 'harris_block': 3,
        'harris_size': 3, 'subpixel': True, 'sift_contrast': .04, 'sift_edge': 10,
        'sift_sigma': 1.6, 'orb_scale': 1.2, 'orb_levels': 8, 'orb_fast': 20, 'orb_patch': 31},
    '07_radiomica': {'mode': 'count', 'bin_counts': [32,16,64], 'bin_widths': [8,4,16],
        'low': 0, 'high': 255, 'distance_sets': '1', 'alpha': 0},
}


def digest(value):
    """Identifica contenido JSON de modo estable, independiente del orden de las claves."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def load_regions(path):
    """Lee un archivo Shapes guardado por Napari, rasteriza y conserva sus nombres y vértices."""
    path = Path(path)
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    shape = tuple(data['image_shape'])
    result = []
    for layer_index, layer in enumerate(data['layers']):
        if layer['kind'] != 'Shapes':
            continue
        if not np.allclose(layer.get('scale', [1,1]), 1) or not np.allclose(layer.get('translate', [0,0]), 0):
            raise ValueError('Las regiones deben estar en coordenadas de píxel sin transformaciones.')
        if not np.allclose(layer.get('affine', np.eye(3)), np.eye(3)):
            raise ValueError('La capa Shapes tiene una transformación no admitida.')
        shapes = Shapes([np.asarray(a) for a in layer['data']], shape_type=layer['shape_type'], ndim=2)
        features = layer.get('features', {})
        for i, mask in enumerate(shapes.to_masks(mask_shape=shape)):
            identifier = features.get('roi_id', [f'ROI_{k+1}' for k in range(len(layer['data']))])[i]
            if not str(identifier).strip():
                raise ValueError('Cada ROI debe tener un nombre no vacío.')
            result.append(dict(id=str(identifier), tipo=features.get('tipo', ['tejido']*len(layer['data']))[i],
                fondo_id=features.get('fondo_id', ['']*len(layer['data']))[i],
                mask=mask.astype(bool), hash=array_hash(mask.astype(np.uint8)),
                layer_index=layer_index, index=i, layer_name=layer['name'],
                geometry=dict(shape_type=layer['shape_type'][i], vertices_fila_columna=layer['data'][i])))
    if len({x['id'] for x in result}) != len(result):
        raise ValueError('Hay nombres de ROI repetidos; asignar IDs únicos.')
    if not result:
        raise ValueError('El archivo no contiene figuras Shapes.')
    return data, result


def configurations(activity, settings):
    """Expande barridos explícitos; LBP usa pares P:R, nunca un producto cartesiano implícito."""
    p = copy.deepcopy(settings)
    if activity == '04_lbp':
        pairs = [s.strip().split(':') for s in p.pop('pairs').split(';') if s.strip()]
        if not pairs or any(len(s) != 2 for s in pairs):
            raise ValueError('LBP: escribir pares como 8:1;16:2;24:3.')
        return [dict(p, points=int(a), radius=float(b)) for a,b in pairs]
    if activity == '04_wavelet':
        return [dict(p, level=int(v)) for v in p.pop('levels')]
    if activity == '03_estructura':
        return [dict(p, prune_length=float(v)) for v in p.pop('prune_lengths')]
    if activity == '06_puntos':
        p.pop('pair_mode', None)
        return [dict(p, method=m) for m in p.pop('methods')]
    if activity == '07_radiomica':
        counts, widths = p.pop('bin_counts'), p.pop('bin_widths')
        distance_sets=[[int(v.strip()) for v in group.split(',') if v.strip()] for group in p.pop('distance_sets').split(';') if group.strip()]
        if not distance_sets or any(not values or min(values)<1 for values in distance_sets):
            raise ValueError('Distancias: usar conjuntos como 1;2;4 o 1,2;3,4.')
        if p['mode'] == 'count':
            return [dict(p, bins=int(v), width=8, distances=ds) for v,ds in product(counts,distance_sets)]
        return [dict(p, bins=32, width=float(v), distances=ds) for v,ds in product(widths,distance_sets)]
    return [p]


def roi_context(image_meta, region):
    """Registra origen y geometría de la figura realmente usada, sin depender de la selección visual."""
    return dict(imagen_id=image_meta['case_id'], variante=image_meta['variant'], roi_id=region['id'],
        capa_imagen=image_meta['layer_name'], capa_region=region['layer_name'], indice_region=region['index']+1,
        roi_geometria=region['geometry'], fuente=image_meta, coordinate_frame='row,col; px; sin transformaciones')


def prepare_tasks(project, region_path, activities, selected_images, selected_rois, settings, options):
    """Congela imágenes, máscaras y configuraciones seleccionadas para un lote reproducible."""
    project = Path(project)
    _, regions = load_regions(region_path)
    regions = [r for r in regions if r['id'] in selected_rois]
    pool = dict((meta['layer_name'], (image,meta)) for image,meta in load_pool(project))
    tasks = []
    for activity in activities:
        configs = configurations(activity, settings[activity])
        image_names = [n for n in selected_images if n in pool]
        pairs = []
        if activity == '06_puntos':
            mode = settings[activity]['pair_mode']
            for name in image_names:
                image,meta = pool[name]
                if meta['variant'] == 'original':
                    continue
                if mode == 'original_procesada':
                    original = next((n for n,(a,m) in pool.items() if m['case_id']==meta['case_id'] and m['variant']=='original'),None)
                else:
                    original = next((n for n,(a,m) in pool.items() if m['case_id']=='Retina1_2' and m['variant']=='original'),None)
                if original:
                    # La fila representa la versión estudiada (A), comparada con la original/referencia B.
                    pairs.append((name,original))
        else:
            pairs = [(n,None) for n in image_names]
        for (name,name_b), region, params in product(pairs, regions, configs):
            if activity in ('00_segmentacion','02_geometria','03_estructura') and region['tipo']!='vascular':
                continue
            tasks.append(dict(activity=activity, image_name=name, image_b_name=name_b,
                region=region, params=copy.deepcopy(params), options=copy.deepcopy(options)))
    return tasks, pool


def segment_key(image_meta, region):
    """Ruta estable para una pareja imagen/ROI; las revisiones antiguas se archivan por contenido."""
    return digest(dict(image=image_meta['layer_name'], roi=region['id']))[:20]


def segmentation_path(root, image_meta, region):
    """Localiza la máscara persistente de una pareja imagen/ROI."""
    return Path(root)/'segmentaciones'/segment_key(image_meta,region)/'segmentacion.json'


def read_segmentation(root, image_meta, region):
    """Lee metadatos y máscara sin asumir que una segmentación automática fue aprobada."""
    path = segmentation_path(root,image_meta,region)
    if not path.exists():
        return None
    record = json.loads(path.read_text(encoding='utf-8'))
    record['_path'] = str(path)
    record['mask'] = tifffile.imread(path.parent/record['archivo_mascara'])>0
    return record


def save_segmentation(root, image, meta, region, mask, params, threshold, approved=False, edited=False, note=''):
    """Conserva máscara por contenido y metadatos de revisión, preservando versiones anteriores."""
    path = segmentation_path(root,meta,region)
    path.parent.mkdir(parents=True,exist_ok=True)
    mask = np.asarray(mask,bool)&region['mask']
    mh = array_hash(mask.astype(np.uint8))
    filename = f'mascara_{mh[:20]}.tif'
    tifffile.imwrite(path.parent/filename,mask.astype(np.uint8),compression='deflate')
    record = dict(imagen=meta['layer_name'],imagen_hash=array_hash(image),roi_id=region['id'],
        roi_hash=region['hash'],archivo_mascara=filename,mascara_hash=mh,parametros=params,
        umbral_efectivo=threshold,aprobada=bool(approved),editada_manualmente=bool(edited),nota_revision=note)
    version = digest(record)
    write_json(path.parent/f'revision_{version[:16]}.json',record)
    write_json(path,record)
    return record


def approve_segmentation(root, image, meta, region, mask=None, note='Revisada visualmente por el usuario'):
    """Aprueba o actualiza una máscara tras una decisión explícita del usuario."""
    rec = read_segmentation(root,meta,region)
    if rec is None:
        raise ValueError('Primero generar la segmentación.')
    if rec['imagen_hash']!=array_hash(image) or rec['roi_hash']!=region['hash']:
        raise ValueError('La imagen o ROI cambió: generar una máscara para los datos actuales.')
    actual = rec['mask'] if mask is None else np.asarray(mask,bool)&region['mask']
    return save_segmentation(root,image,meta,region,actual,rec['parametros'],rec['umbral_efectivo'],
        approved=True,edited=rec['editada_manualmente'] or not np.array_equal(actual,rec['mask']),note=note)


def task_signature(activity, context, params, image, region, background, vessels, image_b):
    """Incluye todos los datos que pueden cambiar una medición para omitir solo repeticiones exactas."""
    return digest(dict(activity=activity,imagen=context['capa_imagen'],roi=region['id'],
        roi_hash=region['hash'],imagen_hash=array_hash(image),params=params,
        background=None if background is None else array_hash(background.astype(np.uint8)),
        vessels=None if vessels is None else array_hash(vessels.astype(np.uint8)),
        image_b=None if image_b is None else array_hash(image_b)))


def execute_task(project, root, task, pool, all_regions, completed):
    """Ejecuta una combinación, valida fondo/segmentación y guarda inmediatamente el resultado."""
    activity, region, params = task['activity'],task['region'],task['params']
    options = task['options']
    image, meta = pool[task['image_name']]
    image_b = None if task['image_b_name'] is None else pool[task['image_b_name']][0]
    context = roi_context(meta,region)
    context.update(propiedad=options.get('propiedad',''),justificacion=options.get('justificacion',''),
        parametros_solicitados=params, actividad_solicitada=activity)
    if activity=='00_segmentacion':
        previous = read_segmentation(root,meta,region)
        if previous and previous['parametros']==params and previous['imagen_hash']==array_hash(image) and previous['roi_hash']==region['hash'] and options.get('skip_existing',True):
            return dict(estado='omitida',detalle='Máscara existente conservada',**context)
        mask,response,threshold = segment_vessels(image,region['mask'],**params)
        rec=save_segmentation(root,image,meta,region,mask,params,threshold)
        fig=segmentation_figure(image,region['mask'],mask,context)
        fig.savefig(segmentation_path(root,meta,region).parent/'vista.png',dpi=120)
        fig.clear()
        return dict(estado='guardada',detalle='Máscara pendiente de revisión',**context)
    background = None
    if activity=='01_intensidad' and options.get('correct_background',True) and region['fondo_id']:
        reference = next((r for r in all_regions if r['id']==region['fondo_id']),None)
        if reference is None:
            raise ValueError(f"No existe la ROI de fondo {region['fondo_id']}")
        if np.any(region['mask']&reference['mask']):
            raise ValueError(f"{region['id']} se superpone con el fondo {reference['id']}; elegir otro fondo o dejarlo sin corrección.")
        background = reference['mask']
        context['fondo_roi_id'] = reference['id']
        context['fondo_geometria'] = reference['geometry']
    vessels = None
    if activity in ('02_geometria','03_estructura'):
        rec = read_segmentation(root,meta,region)
        if rec is None or not rec['aprobada']:
            raise ValueError('Falta máscara vascular aprobada en Revisión de máscaras.')
        if rec['roi_hash']!=region['hash'] or rec['imagen_hash']!=array_hash(image):
            raise ValueError('Máscara de otra imagen o ROI modificada; volver a segmentar.')
        vessels = rec['mask']&region['mask']
        context['segmentacion'] = {k:v for k,v in rec.items() if k not in ('mask','_path')}
    effective_activity = '02_geometria' if activity=='02_forma_roi' else activity
    if activity=='02_forma_roi':
        context['interpretacion_forma']='Contorno de ROI dibujada; no es geometría de un vaso segmentado.'
    if image_b is not None:
        context['imagen_b_fuente']=pool[task['image_b_name']][1]
    signature = task_signature(activity,context,params,image,region,background,vessels,image_b)
    if options.get('skip_existing',True) and signature in completed:
        return dict(estado='omitida',detalle='Medición idéntica ya guardada',**context)
    context['firma_lote']=signature
    result=run(effective_activity,image,region['mask'],params,context,background=background,vessels=vessels,image_b=image_b)
    # Los mapas completos son opcionales: siempre se preservan los datos para recalcularlos.
    if not options.get('save_maps',False):
        keep={'histograma','esqueleto','mascara_medida','extremos','bifurcaciones','puntos_a','puntos_b',
              'descriptores_a','descriptores_b','tamanos_a','tamanos_b','angulos_a','angulos_b'}
        result['arrays']={k:v for k,v in result['arrays'].items() if k in keep or k.startswith('rama_')}
    context['mapas_completos_guardados']=options.get('save_maps',False)
    result['context']=context
    identity=save_measurement(root,result)
    path=Path(root)/'mediciones'/identity
    fig=measurement_figure(result)
    fig.savefig(path/'figura.png',dpi=120)
    fig.clear()
    completed.add(signature)
    return dict(estado='guardada',detalle=f'mediciones/{identity}',medicion_id=identity,**context)


def execute_batch(project, root, region_path, tasks, pool, progress=None, cancelled=None):
    """Procesa en serie, continúa ante errores y guarda progreso suficiente para reanudar."""
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    _,regions=load_regions(region_path)
    records=read_records(root)
    completed={r.get('firma_lote') for r in records if r.get('firma_lote')}
    # Reconoce también mediciones iniciales equivalentes, anteriores al soporte de lotes.
    for rec in records:
        if rec.get('firma_lote') or rec['actividad']!='01_intensidad':
            continue
        if rec['parametros']!=DEFAULTS['01_intensidad']:
            continue
        region=next((r for r in regions if r['id']==rec['roi_id'] and r['hash']==rec['roi_hash']),None)
        name=rec.get('capa_imagen')
        if region is None or name not in pool:
            continue
        image=pool[name][0]
        background=None if 'fondo_snapshot' not in rec else tifffile.imread(root/rec['fondo_snapshot'])>0
        completed.add(task_signature('01_intensidad',rec,DEFAULTS['01_intensidad'],image,region,background,None,None))
    reports=[]
    for i,task in enumerate(tasks):
        if cancelled and cancelled():
            break
        try:
            report=execute_task(project,root,task,pool,regions,completed)
        except Exception as exc:
            report=dict(estado='error',detalle=str(exc),actividad_solicitada=task['activity'],
                capa_imagen=task['image_name'],roi_id=task['region']['id'],parametros_solicitados=task['params'],
                diagnostico=traceback.format_exc())
        reports.append(report)
        write_json(root/'ultimo_lote.json',dict(total=len(tasks),procesadas=len(reports),cancelado=len(reports)<len(tasks),filas=reports))
        if progress:
            progress(i+1,len(tasks),report)
    return reports


def segmentation_figure(image, roi, mask, context):
    """Muestra imagen y máscara recortadas al entorno de la ROI para revisión visual."""
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    yy,xx=np.where(roi);a,b=max(0,yy.min()-5),min(image.shape[0],yy.max()+6);c,d=max(0,xx.min()-5),min(image.shape[1],xx.max()+6)
    fig=Figure(figsize=(8,4),layout='constrained');FigureCanvasAgg(fig)
    for ax in fig.subplots(1,2):
        ax.imshow(image[a:b,c:d],cmap='gray',vmin=0,vmax=255);ax.axis('off')
    fig.axes[0].set_title('Imagen en ROI')
    fig.axes[1].imshow(np.ma.masked_where(~mask[a:b,c:d],mask[a:b,c:d]),cmap='spring',alpha=.65,vmin=0,vmax=1)
    fig.axes[1].set_title('Máscara vascular · revisar')
    fig.suptitle(f"{context.get('capa_imagen','')} / {context.get('roi_id','')}")
    return fig


def export_mask_sheets(project, root, region_path):
    """Genera una lámina por ROI con todas las máscaras disponibles y su estado de revisión."""
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    _,regions=load_regions(region_path);pool=load_pool(project);paths=[]
    for region in regions:
        items=[(im,meta,read_segmentation(root,meta,region)) for im,meta in pool]
        items=[x for x in items if x[2] is not None]
        if not items:continue
        fig=Figure(figsize=(13,3.5*((len(items)+3)//4)),layout='constrained');FigureCanvasAgg(fig)
        axes=fig.subplots((len(items)+3)//4,4,squeeze=False).ravel()
        y,x=np.where(region['mask']);sl=np.s_[max(0,y.min()-4):min(region['mask'].shape[0],y.max()+5),max(0,x.min()-4):min(region['mask'].shape[1],x.max()+5)]
        for ax,(im,meta,rec) in zip(axes,items):
            ax.imshow(im[sl],cmap='gray',vmin=0,vmax=255)
            ax.imshow(np.ma.masked_where(~rec['mask'][sl],rec['mask'][sl]),cmap='spring',alpha=.6,vmin=0,vmax=1)
            ax.set_title(meta['layer_name']+'\n'+('APROBADA' if rec['aprobada'] else 'PENDIENTE'),fontsize=8);ax.axis('off')
        for ax in axes[len(items):]:ax.axis('off')
        fig.suptitle(region['id']+' · revisar las máscaras superpuestas')
        name='revision_'+digest(region['id'])[:10]+'.png';path=Path(root)/name;fig.savefig(path,dpi=130);fig.clear();paths.append(str(path))
    return paths
