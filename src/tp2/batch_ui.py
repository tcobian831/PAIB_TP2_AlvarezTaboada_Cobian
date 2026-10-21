"""Interfaz de trabajo por lotes con ROIs guardadas en capas Shapes editables."""

from pathlib import Path
import json
import copy
import threading
import numpy as np
import tifffile
from qtpy.QtCore import QThread, Signal, Qt, QUrl, QEvent
from qtpy.QtGui import QDesktopServices
from qtpy.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QPushButton,
    QComboBox,QLineEdit,QCheckBox,QTabWidget,QScrollArea,QTableWidget,QTableWidgetItem,
    QProgressBar,QPlainTextEdit,QFileDialog,QHeaderView,QAbstractItemView,QMessageBox,QInputDialog)
from napari.layers import Shapes
from . import workflow as wf
from .data import load_pool, save_regions
from .storage import write_json
from .comparison import build_matrix

LABELS={
 'percentiles':'Percentiles [%]', 'sigmas':'Escalas sigma [px]', 'threshold':'Umbral Frangi (vacío = Otsu)',
 'min_size':'Área mínima de componente [px²]','closing':'Radio del cierre [px]','fill_holes':'Área máxima de huecos [px²]',
 'prune_lengths':'Longitudes de poda a comparar [px]','calculate_thickness':'Calcular espesor local',
 'pairs':'Pares LBP P:R, separados por ;','method':'Codificación LBP','wavelengths':'Longitudes de onda Gabor [px]',
 'angles':'Orientaciones normales Gabor [°]','sigma_ratio':'Gabor sigma/lambda','gamma':'Gabor gamma',
 'wavelet':'Familia Wavelet','levels':'Niveles Wavelet a comparar','dog_k':'Relación de escalas DoG',
 'methods':'Detectores a comparar','pair_mode':'Comparación de puntos','max_points':'Máximo de puntos',
 'ratio':'Umbral del cociente de distancias','mutual':'Exigir vecino mutuo','tolerance':'Tolerancia espacial [px]',
 'low':'Límite común inferior de intensidad','high':'Límite común superior de intensidad','harris_k':'Harris k',
 'harris_threshold':'Harris umbral relativo','min_distance':'Harris separación mínima [px]',
 'harris_block':'Harris tamaño de bloque','harris_size':'Harris apertura Sobel','subpixel':'Refinar posición Harris',
 'sift_contrast':'SIFT umbral de contraste','sift_edge':'SIFT umbral de borde','sift_sigma':'SIFT sigma inicial',
 'orb_scale':'ORB factor de escala','orb_levels':'ORB niveles de pirámide','orb_fast':'ORB umbral FAST',
 'orb_patch':'ORB tamaño de parche impar [px]','mode':'Discretización','bin_counts':'Cantidades de bins a comparar',
 'bin_widths':'Anchos de bin a comparar [u.a.]','distance_sets':'Conjuntos de distancias [px]: 1;2;4','alpha':'GLDM alpha',
}


def button(text, callback):
    """Crea un botón conectado a una acción concreta del panel."""
    widget=QPushButton(text)
    def invoke(*_):
        """Muestra errores de una acción sin cerrar la aplicación."""
        try:callback()
        except Exception as exc:QMessageBox.warning(widget.window(), 'No se completó la acción', str(exc))
    widget.clicked.connect(invoke)
    return widget


def checked_item(text, checked=True):
    """Crea una casilla de selección en una tabla, sin edición accidental del identificador."""
    item=QTableWidgetItem(text);item.setFlags(Qt.ItemIsEnabled|Qt.ItemIsSelectable|Qt.ItemIsUserCheckable)
    item.setCheckState(Qt.Checked if checked else Qt.Unchecked);return item


class BatchWorker(QThread):
    """Ejecuta cálculos secuenciales fuera del hilo de la interfaz y comunica cada resultado."""
    tick=Signal(int,int,object)
    result=Signal(object)
    failed=Signal(str)

    def __init__(self, function):
        """Recibe una función que acepta emisor de progreso y consulta de cancelación."""
        super().__init__();self.function=function;self.stop=threading.Event()

    def run(self):
        """Captura errores del lote sin cerrar la ventana y conserva todo lo ya guardado."""
        try:self.result.emit(self.function(self.tick.emit,self.stop.is_set))
        except Exception:
            import traceback
            self.failed.emit(traceback.format_exc())


class Panel(QWidget):
    """Organiza selección persistente, parámetros, ejecución por lotes y revisión de resultados."""
    def __init__(self, viewer, project):
        """Carga imágenes y Shapes del proyecto; las posiciones se leen exclusivamente del JSON."""
        super().__init__();self.viewer=viewer;self.project=Path(project)
        self.root=self.project/'resultados';self.region_path=self.project/'rois/seleccion_final/regiones.json'
        self.settings=copy.deepcopy(wf.DEFAULTS);self.roi_choices={};self.worker=None;self.roi_layers=[]
        self.current_activity=None;self.fields={};self.loaded_review=None;self.busy=False
        self.pool={m['layer_name']:(a,m) for a,m in load_pool(self.project)}
        self.payload,self.regions=wf.load_regions(self.region_path)
        self.state_path=self.project/'config/sesion.json'
        if self.state_path.exists():
            state=json.loads(self.state_path.read_text(encoding='utf-8'))
            for k,v in state.get('parametros',{}).items():
                if k in self.settings:self.settings[k].update({name:value for name,value in v.items() if name in self.settings[k]})
            self.roi_choices=state.get('seleccion_rois',{})
        layout=QVBoxLayout(self)
        title=QLabel('TP2 · Regiones persistentes y procesamiento por lotes');title.setWordWrap(True);layout.addWidget(title)
        self.tabs=QTabWidget();layout.addWidget(self.tabs)
        self._regions_tab();self._batch_tab();self._review_tab();self._results_tab()
        self.progress=QProgressBar();layout.addWidget(self.progress)
        self.status=QLabel('Listo. Regiones cargadas desde el archivo del proyecto.');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.log=QPlainTextEdit();self.log.setReadOnly(True);self.log.setMaximumHeight(140);layout.addWidget(self.log)
        self._load_layers();self._fill_region_table();self._change_activity();self._refresh_review()
        self.setMinimumWidth(510)
        viewer.window._qt_window.installEventFilter(self)

    def eventFilter(self, watched, event):
        """Solicita detener el lote antes de cerrar para no destruir un hilo de cálculo activo."""
        if event.type()==QEvent.Close and self.busy:
            self._cancel();event.ignore();return True
        return super().eventFilter(watched,event)

    def _highlight_roi(self,row,column):
        """Selecciona en Shapes la figura de una fila de la tabla de nombres."""
        if row<0 or row>=len(self.regions):return
        region=self.regions[row]
        for layer in self.roi_layers:
            layer.selected_data={region['index']} if layer.name==region['layer_name'] else set()
            if layer.name==region['layer_name']:
                self.viewer.layers.selection.active=layer;layer.mode='select'

    def _tab(self,title):
        """Crea una pestaña desplazable para que todos los controles sean accesibles."""
        body=QWidget();layout=QVBoxLayout(body);scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(body)
        self.tabs.addTab(scroll,title);return layout

    def _regions_tab(self):
        """Expone nombres, tipo y fondo asignado de cada Shape, sin números de figura manuales."""
        layout=self._tab('1 · ROIs')
        label=QLabel('Regiones cargadas desde rois/seleccion_final/regiones.json.\nLas figuras Shapes son editables. Cada región tiene un identificador y un fondo asignado.');label.setWordWrap(True);layout.addWidget(label)
        self.region_table=QTableWidget(0,4);self.region_table.setHorizontalHeaderLabels(['Nombre permanente','Tipo','Fondo asignado','Píxeles'])
        self.region_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents);self.region_table.cellClicked.connect(self._highlight_roi);layout.addWidget(self.region_table)
        layout.addWidget(button('Mostrar ROIs sobre Retina1',self._show_regions))
        layout.addWidget(button('Guardar nombres y cambios hechos en Shapes',self._save_shapes))
        layout.addWidget(button('Duplicar una ROI para evaluar sensibilidad a sus bordes',self._duplicate_roi))
        layout.addWidget(button('Importar otro regiones.json…',self._import_regions))
        label=QLabel('Tipo vascular: habilita segmentación, forma de vasos y estructura.\nTipo fondo: no se corrige contra sí mismo.\nTipo tejido: intensidad, textura y radiómica.\nAsignar fondo no demuestra que represente bien la iluminación local; evaluar esa elección.');label.setWordWrap(True);layout.addWidget(label)
        layout.addStretch()

    def _batch_tab(self):
        """Permite elegir imágenes y ROIs una vez, configurar barridos y ejecutar lotes completos."""
        layout=self._tab('2 · Lotes')
        self.images=QTableWidget(0,1);self.images.setHorizontalHeaderLabels(['Imágenes incluidas en el lote']);self.images.setRowCount(len(self.pool));self.images.setMinimumHeight(240)
        for i,name in enumerate(self.pool):self.images.setItem(i,0,checked_item(name))
        self.images.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);layout.addWidget(self.images)
        row=QHBoxLayout();row.addWidget(button('Todas',lambda:self._select_images('todas')));row.addWidget(button('12 principales',lambda:self._select_images('principales')));row.addWidget(button('Solo referencia',lambda:self._select_images('referencia')));layout.addLayout(row)
        self.activity=QComboBox()
        for key,name in wf.ACTIVITIES.items():self.activity.addItem(name,key)
        self.activity.currentIndexChanged.connect(self._change_activity);layout.addWidget(self.activity)
        self.roi_select=QTableWidget(0,1);self.roi_select.setHorizontalHeaderLabels(['ROIs para esta actividad']);self.roi_select.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);self.roi_select.setMinimumHeight(170);layout.addWidget(self.roi_select)
        self.parameter_box=QWidget();self.parameter_form=QFormLayout(self.parameter_box);layout.addWidget(self.parameter_box)
        self.background=QCheckBox('Intensidad: incluir corrección con el fondo asignado');self.background.setChecked(True);layout.addWidget(self.background)
        self.skip=QCheckBox('Omitir cálculos idénticos ya completados');self.skip.setChecked(True);layout.addWidget(self.skip)
        self.maps=QCheckBox('Guardar también todos los mapas completos (más espacio y tiempo)');layout.addWidget(self.maps)
        self.goal=QLineEdit();self.goal.setPlaceholderText('Propiedad a describir (se registra para el lote)');layout.addWidget(self.goal)
        self.reason=QLineEdit();self.reason.setPlaceholderText('Justificación de regiones, parámetros y orden');layout.addWidget(self.reason)
        self.preview=QLabel();self.preview.setWordWrap(True);layout.addWidget(self.preview)
        layout.addWidget(button('Ver cantidad de cálculos y guardar plan',self._preview))
        self.run_current=button('Ejecutar actividad seleccionada',self._run_current);layout.addWidget(self.run_current)
        self.run_basic=button('Ejecutar intensidad + textura + escala + puntos + radiómica',self._run_basic);layout.addWidget(self.run_basic)
        note=QLabel('El botón combinado usa la selección de ROIs y parámetros guardada para cada actividad.\nForma y estructura se ejecutan después de aprobar las máscaras en la pestaña 3.');note.setWordWrap(True);layout.addWidget(note)
        self.cancel=button('Detener al terminar el cálculo actual',self._cancel);layout.addWidget(self.cancel)

    def _review_tab(self):
        """Revisión de máscaras por imagen/ROI con edición Labels y aprobación individual o en grupo."""
        layout=self._tab('3 · Máscaras')
        label=QLabel('Primero ejecutá «Preparar máscaras vasculares». Revisá las superposiciones antes de medir forma o estructura. Las máscaras generadas no se aprueban automáticamente.');label.setWordWrap(True);layout.addWidget(label)
        self.review_table=QTableWidget(0,4);self.review_table.setHorizontalHeaderLabels(['Imagen','ROI','Estado','Píxeles']);self.review_table.setSelectionBehavior(QAbstractItemView.SelectRows);self.review_table.setSelectionMode(QAbstractItemView.ExtendedSelection);self.review_table.setEditTriggers(QAbstractItemView.NoEditTriggers);self.review_table.setMinimumHeight(300);layout.addWidget(self.review_table)
        layout.addWidget(button('Actualizar lista',self._refresh_review))
        layout.addWidget(button('Abrir máscara elegida para revisar / pintar',self._open_review))
        layout.addWidget(button('Guardar edición y aprobar máscara abierta',self._approve_open))
        layout.addWidget(button('Aprobar máscaras seleccionadas',self._approve_selected))
        layout.addWidget(button('Crear láminas con todas las superposiciones',self._sheets))
        layout.addWidget(button('Medir forma y estructura de las máscaras aprobadas',self._run_vascular))
        note=QLabel('Seleccionar varias filas con Ctrl o Shift; Ctrl+A selecciona toda la tabla. La aprobación confirma la revisión visual de la máscara. La poda y el espesor se configuran en «Estructura vascular» de la pestaña 2.');note.setWordWrap(True);layout.addWidget(note)

    def _results_tab(self):
        """Muestra resultados, permite abrir evidencia y construir la comparación global."""
        layout=self._tab('4 · Resultados')
        self.results=QTableWidget(0,4);self.results.setHorizontalHeaderLabels(['Estado','Actividad','Imagen / ROI','Detalle']);self.results.setEditTriggers(QAbstractItemView.NoEditTriggers);self.results.setSelectionBehavior(QAbstractItemView.SelectRows);self.results.setMinimumHeight(250);layout.addWidget(self.results)
        layout.addWidget(button('Abrir figura del resultado elegido',self._open_result))
        layout.addWidget(button('Construir matriz global y comparaciones',self._global))
        layout.addWidget(button('Abrir carpeta resultados',lambda:self._open(self.root)))
        layout.addWidget(button('Guardar captura actual del visor',self._capture))
        layout.addWidget(button('Abrir CSV de intensidad',self._legacy))
        self.global_info=QLabel('Las variantes de LBP, Wavelet, radiómica y los tres detectores se conservan por separado en la matriz.');self.global_info.setWordWrap(True);layout.addWidget(self.global_info)

    def _open(self,path):
        """Abre un archivo o carpeta existente con la aplicación del sistema."""
        path=Path(path)
        if not path.exists():raise ValueError(f'No existe {path}')
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

    def _load_layers(self):
        """Reconstruye imágenes y capas Shapes desde archivos, conservando las figuras editables."""
        for name,(image,meta) in self.pool.items():
            if name not in self.viewer.layers:
                self.viewer.add_image(image,name=name,metadata=meta,colormap='gray',contrast_limits=(0,255),visible=False)
        self.roi_layers=[]
        for rec in self.payload['layers']:
            if rec['kind']!='Shapes':continue
            layer=self.viewer.add_shapes([np.asarray(a) for a in rec['data']],shape_type=rec['shape_type'],name=rec['name'],features=rec.get('features',{}),edge_color='lime',face_color=[0,1,0,.08],edge_width=1.5)
            self.roi_layers.append(layer)
        self._show_regions()

    def _show_regions(self):
        """Muestra la imagen de referencia y las figuras guardadas sin alterar sus coordenadas."""
        reference=next(n for n,(a,m) in self.pool.items() if m['case_id']=='Retina1_2' and m['variant']=='original')
        for name in self.pool:self.viewer.layers[name].visible=name==reference
        for layer in self.roi_layers:layer.visible=True
        self.viewer.reset_view()

    def _fill_region_table(self):
        """Presenta una fila editable por figura y mantiene el orden original de Shapes."""
        self.region_table.setRowCount(len(self.regions))
        names=['Sin corrección']+[r['id'] for r in self.regions]
        for i,r in enumerate(self.regions):
            self.region_table.setItem(i,0,QTableWidgetItem(r['id']))
            kind=QComboBox();kind.addItems(['vascular','fondo','tejido']);kind.setCurrentText(r['tipo']);self.region_table.setCellWidget(i,1,kind)
            bg=QComboBox();bg.addItems(names);bg.setCurrentText(r['fondo_id'] or 'Sin corrección');self.region_table.setCellWidget(i,2,bg)
            item=QTableWidgetItem(str(int(r['mask'].sum())));item.setFlags(Qt.ItemIsEnabled);self.region_table.setItem(i,3,item)

    def _save_shapes(self):
        """Guarda vértices editados y propiedades en el JSON original, con respaldo previo."""
        if self.busy:raise ValueError('Esperar o detener el lote antes de modificar las regiones.')
        for layer in self.roi_layers:
            old=[r for r in self.regions if r['layer_name']==layer.name]
            if len(layer.data)!=len(old):
                raise ValueError('Para agregar/eliminar figuras, importar un regiones.json con IDs únicos; este guardado conserva las cinco figuras existentes.')
            ids=[];kinds=[];backgrounds=[]
            for region in old:
                row=next(i for i,r in enumerate(self.regions) if r is region)
                ids.append(self.region_table.item(row,0).text().strip());kinds.append(self.region_table.cellWidget(row,1).currentText())
                value=self.region_table.cellWidget(row,2).currentText();backgrounds.append('' if value=='Sin corrección' else value)
            if len(set(ids))!=len(ids) or not all(ids):raise ValueError('Los nombres deben ser únicos y no vacíos.')
            layer.features={'roi_id':ids,'tipo':kinds,'fondo_id':backgrounds}
        backup=self.region_path.with_name('regiones_respaldo.json')
        if not backup.exists():backup.write_bytes(self.region_path.read_bytes())
        save_regions(self.region_path.parent,self.roi_layers,next(iter(self.pool.values()))[0].shape)
        self.payload,self.regions=wf.load_regions(self.region_path);self._fill_region_table();self._change_activity()
        self.status.setText('ROIs y propiedades guardadas. Los resultados previos conservan sus máscaras originales.')

    def _duplicate_roi(self):
        """Duplica una figura como nueva ROI identificada, dejando intacta la selección original."""
        if self.busy:
            raise ValueError('Esperar al final del lote.')
        self._save_shapes()
        name,ok=QInputDialog.getItem(self,'Duplicar ROI','Elegir región',[r['id'] for r in self.regions],0,False)
        if not ok:return
        region=next(r for r in self.regions if r['id']==name)
        new_name,ok=QInputDialog.getText(self,'Nombre de la nueva ROI','ID único',text=name+'_ampliada')
        if not ok:return
        new_name=new_name.strip()
        if not new_name or new_name in [r['id'] for r in self.regions]:
            raise ValueError('Asignar un ID nuevo y no vacío.')
        layer=next(l for l in self.roi_layers if l.name==region['layer_name'])
        properties=layer.features.to_dict(orient='list')
        layer.add(np.array(region['geometry']['vertices_fila_columna']),shape_type=region['geometry']['shape_type'])
        properties['roi_id'].append(new_name)
        properties['tipo'].append(region['tipo'])
        properties['fondo_id'].append(region['fondo_id'])
        layer.features=properties
        layer.selected_data={len(layer.data)-1};layer.mode='select'
        save_regions(self.region_path.parent,self.roi_layers,next(iter(self.pool.values()))[0].shape)
        self.payload,self.regions=wf.load_regions(self.region_path)
        self._fill_region_table();self._change_activity()
        self.status.setText('Copia creada. Ajustar los bordes con Shapes y guardar los cambios antes de incluir la nueva ROI en el lote de radiómica.')

    def _import_regions(self):
        """Importa un archivo de regiones del usuario y lo usa como selección editable activa."""
        path,_=QFileDialog.getOpenFileName(self,'Abrir regiones.json',str(self.project/'rois'),'JSON (*.json)')
        if not path:return
        payload,regions=wf.load_regions(path)
        if tuple(payload['image_shape'])!=next(iter(self.pool.values()))[0].shape:raise ValueError('Dimensiones incompatibles.')
        for layer in self.roi_layers:self.viewer.layers.remove(layer)
        self.region_path=Path(path);self.payload,self.regions=payload,regions;self._load_layers();self._fill_region_table();self.roi_choices={};self._change_activity()

    def _select_images(self,mode):
        """Marca el pool completo, las doce versiones principales o únicamente la referencia."""
        for i,(name,(a,m)) in enumerate(self.pool.items()):
            checked=mode=='todas' or (mode=='principales' and m['variant']!='intermedia') or (mode=='referencia' and m['case_id']=='Retina1_2' and m['variant']=='original')
            self.images.item(i,0).setCheckState(Qt.Checked if checked else Qt.Unchecked)

    def _selected_images(self):
        """Devuelve los nombres de las imágenes marcadas, sin depender de su visibilidad en Napari."""
        return [self.images.item(i,0).text() for i in range(self.images.rowCount()) if self.images.item(i,0).checkState()==Qt.Checked]

    def _default_rois(self,activity):
        """Propone conjuntos por su objetivo, sin obligar a medir todas las familias en todas las ROIs."""
        vascular=[r['id'] for r in self.regions if r['tipo']=='vascular']
        if activity=='01_intensidad':return [r['id'] for r in self.regions]
        if activity in ('00_segmentacion','02_geometria'):return vascular
        if activity in ('03_estructura','06_puntos'):return sorted(vascular,key=lambda n:next(r['mask'].sum() for r in self.regions if r['id']==n),reverse=True)[:1]
        if activity=='05_multiescala':return sorted(vascular,key=lambda n:next(r['mask'].sum() for r in self.regions if r['id']==n))[:2]
        if activity=='02_forma_roi':return [r['id'] for r in self.regions if r['tipo']=='tejido']
        background=[r['id'] for r in self.regions if r['tipo']=='fondo'][:1]
        largest=sorted(vascular,key=lambda n:next(r['mask'].sum() for r in self.regions if r['id']==n),reverse=True)[:1]
        return background+largest

    def _collect_fields(self):
        """Valida y guarda los valores del formulario actual, incluidas listas para barridos."""
        if self.current_activity is None:return
        template=wf.DEFAULTS[self.current_activity];parsed={}
        for key,default in template.items():
            field=self.fields[key]
            if isinstance(field,QCheckBox):value=field.isChecked()
            elif isinstance(field,QComboBox):value=field.currentData() if field.currentData() is not None else field.currentText()
            else:
                text=field.text().strip()
                if default is None:value=None if not text else float(text)
                elif isinstance(default,list):
                    values=[x.strip() for x in text.split(',') if x.strip()]
                    converter=type(default[0]);value=[converter(x) for x in values]
                    if not value:raise ValueError(f'{LABELS.get(key,key)} no puede estar vacío.')
                elif isinstance(default,(int,float)):value=type(default)(text)
                else:value=text
            parsed[key]=value
        wf.configurations(self.current_activity,parsed)
        self.settings[self.current_activity]=parsed
        self.roi_choices[self.current_activity]=[self.roi_select.item(i,0).text() for i in range(self.roi_select.rowCount()) if self.roi_select.item(i,0).checkState()==Qt.Checked]

    def _change_activity(self):
        """Reconstruye el formulario para la actividad y recupera su selección de regiones."""
        try:self._collect_fields()
        except Exception as exc:
            if hasattr(self,'log'):self.log.appendPlainText(str(exc))
        self.current_activity=self.activity.currentData();self.fields={}
        while self.parameter_form.count():
            item=self.parameter_form.takeAt(0)
            if item.widget():item.widget().deleteLater()
        params=self.settings[self.current_activity]
        for key,value in params.items():
            if isinstance(value,bool):field=QCheckBox();field.setChecked(value)
            elif key in ('method','mode','pair_mode'):
                field=QComboBox()
                choices={'method':['uniform','default','ror'],'mode':['count','width'],'pair_mode':['original_procesada','referencia']}[key]
                if key=='pair_mode':
                    field.addItem('Cada procesada frente a su original','original_procesada');field.addItem('Cada versión frente a Retina1','referencia')
                    field.setCurrentIndex(max(0,field.findData(value)))
                else:field.addItems(choices);field.setCurrentText(value)
            else:
                text='' if value is None else ','.join(map(str,value)) if isinstance(value,list) else str(value)
                field=QLineEdit(text)
            self.fields[key]=field;self.parameter_form.addRow(LABELS.get(key,key),field)
        selected=self.roi_choices.get(self.current_activity,self._default_rois(self.current_activity))
        self.roi_select.setRowCount(len(self.regions))
        for i,r in enumerate(self.regions):self.roi_select.setItem(i,0,checked_item(r['id'],r['id'] in selected))

    def _save_state(self):
        """Persiste parámetros y conjuntos de ROIs para volver a abrir el proyecto sin reconfigurar."""
        self._collect_fields()
        write_json(self.state_path,dict(parametros=self.settings,seleccion_rois=self.roi_choices))

    def _options(self):
        """Congela las opciones comunes y las anotaciones del próximo lote."""
        return dict(correct_background=self.background.isChecked(),skip_existing=self.skip.isChecked(),save_maps=self.maps.isChecked(),propiedad=self.goal.text(),justificacion=self.reason.text())

    def _tasks(self,activities):
        """Construye el plan por actividad con sus propios parámetros y selección persistente."""
        self._save_state();tasks=[];pool=None
        for layer in self.roi_layers:
            records=[r for r in self.regions if r['layer_name']==layer.name]
            if len(layer.data)!=len(records) or any(not np.array_equal(layer.data[i],np.asarray(r['geometry']['vertices_fila_columna'])) for i,r in enumerate(records)):
                raise ValueError('Las Shapes tienen cambios sin guardar. Usar Guardar nombres y cambios hechos en Shapes antes del lote.')
        for activity in activities:
            selected=self.roi_choices.get(activity,self._default_rois(activity))
            part,pool=wf.prepare_tasks(self.project,self.region_path,[activity],self._selected_images(),selected,self.settings,self._options());tasks.extend(part)
        if not tasks:raise ValueError('No hay combinaciones seleccionadas para ejecutar.')
        write_json(self.project/'config/ultimo_plan.json',dict(actividades=activities,imagenes=self._selected_images(),rois=self.roi_choices,parametros=self.settings,opciones=self._options(),n_calculos=len(tasks)))
        return tasks,pool

    def _preview(self):
        """Muestra cuántas combinaciones produce la actividad antes de ejecutar."""
        tasks,pool=self._tasks([self.activity.currentData()]);self.preview.setText(f'{len(tasks)} cálculos planificados. No se redibujan las ROIs. El plan quedó guardado.')

    def _run_current(self):
        """Ejecuta todos los pares imagen/ROI de la actividad elegida."""
        self._start([self.activity.currentData()])

    def _run_basic(self):
        """Ejecuta las familias que no requieren una máscara vascular revisada."""
        self._start(['01_intensidad','04_lbp','04_gabor','04_wavelet','05_multiescala','06_puntos','07_radiomica'])

    def _run_vascular(self):
        """Calcula forma y estructura solo sobre máscaras explícitamente aprobadas."""
        self._start(['02_geometria','03_estructura'])

    def _start(self,activities):
        """Inicia un único trabajador y deshabilita acciones que podrían modificar sus datos."""
        if self.busy:return
        tasks,pool=self._tasks(activities)
        self._set_busy(True);self.progress.setRange(0,len(tasks));self.progress.setValue(0)
        self.status.setText(f'Lote de {len(tasks)} cálculos. Se guardan a medida que terminan.')
        self.worker=BatchWorker(lambda progress,cancelled:wf.execute_batch(self.project,self.root,self.region_path,tasks,pool,progress,cancelled))
        self.worker.tick.connect(self._tick);self.worker.result.connect(self._done);self.worker.failed.connect(self._failed);self.worker.start()

    def _set_busy(self,value):
        """Evita cálculos simultáneos y cambios de región mientras se ejecuta un lote."""
        self.busy=value
        for widget in (self.run_current,self.run_basic,self.activity,self.parameter_box,self.images,self.roi_select,self.region_table,self.tabs.widget(0),self.tabs.widget(2)):
            widget.setEnabled(not value)

    def _cancel(self):
        """Pide detener el lote al concluir la tarea actual sin perder resultados guardados."""
        if self.worker and self.busy:self.worker.stop.set();self.status.setText('Se detendrá al finalizar el cálculo actual; lo guardado se conserva.')

    def _tick(self,current,total,record):
        """Actualiza tabla y progreso en el hilo de Qt, sin manipular capas desde el trabajador."""
        self.progress.setValue(current);self.status.setText(f"{current}/{total} · {record['estado']} · {record.get('capa_imagen','')} / {record.get('roi_id','')}")
        row=self.results.rowCount();self.results.insertRow(row)
        values=[record['estado'],record.get('actividad_solicitada',''),record.get('capa_imagen','')+' / '+record.get('roi_id',''),record['detalle']]
        for col,value in enumerate(values):self.results.setItem(row,col,QTableWidgetItem(str(value)))
        self.results.item(row,0).setData(Qt.UserRole,record)
        if record['estado']=='error':self.log.appendPlainText(f"{values[2]}: {record['detalle']}")

    def _done(self,reports):
        """Resume guardados, omitidos y errores e informa que la ejecución fue completa o detenida."""
        from collections import Counter
        count=Counter(r['estado'] for r in reports);self._set_busy(False);self._refresh_review()
        prefix="Lote detenido" if self.worker.stop.is_set() else "Lote terminado"
        self.status.setText(f"{prefix}: {count['guardada']} guardadas, {count['omitida']} omitidas, {count['error']} errores. Detalle en Resultados y ultimo_lote.json.")
        self.worker.wait();self.worker=None

    def _failed(self,message):
        """Muestra un error del proceso sin cerrar Napari ni descartar cálculos previos."""
        self._set_busy(False);self.log.appendPlainText(message);self.status.setText('Error de lote; los resultados ya guardados se conservan.')
        self.worker.wait();self.worker=None

    def _refresh_review(self):
        """Enumera máscaras disponibles y muestra si coinciden con las imágenes y ROIs actuales."""
        self.review_records=[]
        for name,(image,meta) in self.pool.items():
            for region in self.regions:
                rec=wf.read_segmentation(self.root,meta,region)
                if rec is not None:self.review_records.append((name,region,rec))
        self.review_table.setRowCount(len(self.review_records))
        for i,(name,region,rec) in enumerate(self.review_records):
            valid=rec['roi_hash']==region['hash']
            state='DESACTUALIZADA' if not valid else 'APROBADA' if rec['aprobada'] else 'PENDIENTE'
            for j,value in enumerate([name,region['id'],state,int(rec['mask'].sum())]):self.review_table.setItem(i,j,QTableWidgetItem(str(value)))

    def _open_review(self):
        """Carga una máscara guardada en Labels editable sobre la imagen que le corresponde."""
        row=self.review_table.currentRow()
        if row<0:raise ValueError('Seleccionar una fila de máscara.')
        name,region,rec=self.review_records[row]
        for layer_name in self.pool:self.viewer.layers[layer_name].visible=layer_name==name
        for layer in self.roi_layers:layer.visible=False
        for layer_name in ('ROI en revisión','Máscara en revisión'):
            if layer_name in self.viewer.layers:self.viewer.layers.remove(layer_name)
        self.viewer.add_shapes([np.array(region['geometry']['vertices_fila_columna'])],shape_type=region['geometry']['shape_type'],name='ROI en revisión',edge_color='cyan',face_color='transparent',edge_width=2)
        layer=self.viewer.add_labels(rec['mask'].astype(np.uint8),name='Máscara en revisión',opacity=.55);layer.mode='paint'
        self.loaded_review=(name,region,rec['mascara_hash']);self.viewer.reset_view()
        yy,xx=np.where(region['mask']);self.viewer.camera.center=(0,float(yy.mean()),float(xx.mean()));self.viewer.camera.zoom=2 if max(np.ptp(yy),np.ptp(xx))<150 else 1.4
        self.status.setText(f'{name}/{region["id"]}: pintar etiqueta 1 o borrar; luego guardar y aprobar.')

    def _approve_open(self):
        """Guarda la máscara editada y registra aprobación, limitándola a la ROI original."""
        if self.loaded_review is None:raise ValueError('Abrir primero una máscara.')
        name,region,old_hash=self.loaded_review
        layer=self.viewer.layers['Máscara en revisión']
        if not np.allclose(layer.scale,1) or not np.allclose(layer.translate,0) or not np.allclose(layer.affine.affine_matrix,np.eye(3)):raise ValueError('No transformar la capa de máscara.')
        image,meta=self.pool[name];wf.approve_segmentation(self.root,image,meta,region,np.asarray(layer.data)>0)
        self._refresh_review();self.status.setText('Máscara editada guardada y aprobada. Puede medirse forma y estructura.')

    def _approve_selected(self):
        """Registra la aprobación de las filas que el usuario declara haber revisado."""
        rows=sorted({item.row() for item in self.review_table.selectedItems()})
        if not rows:raise ValueError('Seleccionar las máscaras revisadas.')
        for row in rows:
            name,region,rec=self.review_records[row];image,meta=self.pool[name]
            wf.approve_segmentation(self.root,image,meta,region)
        self._refresh_review();self.status.setText(f'{len(rows)} máscaras con revisión visual aprobada.')

    def _sheets(self):
        """Produce láminas de superposiciones y abre cada una para facilitar la revisión en conjunto."""
        paths=wf.export_mask_sheets(self.project,self.root,self.region_path)
        for path in paths:self._open(path)
        self.status.setText(f'{len(paths)} láminas de revisión guardadas en resultados.')

    def _open_result(self):
        """Abre evidencia gráfica de una medición guardada, sin recalcularla."""
        row=self.results.currentRow()
        if row<0:raise ValueError('Elegir una fila de resultados.')
        record=self.results.item(row,0).data(Qt.UserRole)
        if record.get('medicion_id'):self._open(self.root/'mediciones'/record['medicion_id']/'figura.png')
        else:self.log.appendPlainText(record.get('diagnostico',record['detalle']))

    def _global(self):
        """Construye la matriz y las tablas de comparación de las mediciones guardadas."""
        if self.busy:raise ValueError('Esperar al final del lote antes de construir la matriz.')
        frame,changes=build_matrix(self.root)
        self.global_info.setText(f'Matriz guardada: {len(frame)} filas, {len(frame.columns)} columnas. Las configuraciones están separadas y documentadas en 08_seleccion_mediciones.json.')
        self.status.setText('Matriz global y comparaciones exportadas en resultados.')

    def _legacy(self):
        """Abre el CSV que conserva las mediciones iniciales y las posteriores de intensidad."""
        self._open(self.root/'01_intensidad.csv')

    def _capture(self):
        """Guarda una captura del visor como evidencia complementaria a las coordenadas y máscaras."""
        path,_=QFileDialog.getSaveFileName(self,'Guardar captura',str(self.root/'visor.png'),'PNG (*.png)')
        if path:self.viewer.screenshot(path=path,canvas_only=False)
