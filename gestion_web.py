from flask import Flask, render_template_string, request, redirect, url_for, session, flash, send_file
from datetime import datetime, timedelta
import json
import os
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle
import io

# ---------------- CONFIGURACIÓN ----------------
CLAVE_ACCESO = "kio123"
SECRET_KEY = "clave_secreta_segura_2026"
ALCANCE = ['https://www.googleapis.com/auth/drive']
NOMBRE_CARPETA_RAIZ = "Gestion_Procesos_En_Linea"
ARCHIVO_DATOS_NUBE = "procesos_guardados.json"
MAX_OBLIGACIONES = 16

app = Flask(__name__)
app.secret_key = SECRET_KEY

# ---------------- FUNCIONES BASE ----------------
def sumar_dias_habiles(fecha, dias):
    actual = fecha
    while dias > 0:
        actual += timedelta(days=1)
        if actual.weekday() < 5:
            dias -= 1
    return actual

def calcular_dias_restantes(fecha_limite):
    hoy = datetime.now()
    if hoy > fecha_limite:
        return -((hoy - fecha_limite).days)
    temp = hoy
    dias_habiles = 0
    while temp <= fecha_limite:
        if temp.weekday() < 5:
            dias_habiles += 1
        temp += timedelta(days=1)
    return dias_habiles - 1

# ---------------- CONEXIÓN GOOGLE DRIVE ----------------
class ConexionDrive:
    def __init__(self):
        self.servicio = self.autenticar()
        self.id_carpeta_raiz = self.obtener_o_crear_carpeta(NOMBRE_CARPETA_RAIZ, None)

    def autenticar(self):
        credenciales = None
        ruta_base = os.path.dirname(os.path.abspath(__file__))
        ruta_credenciales = os.path.join(ruta_base, 'credentials.json')
        
        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                credenciales = pickle.load(token)
        if not credenciales or not credenciales.valid:
            if credenciales and credenciales.expired and credenciales.refresh_token:
                credenciales.refresh(Request())
            else:
                flujo = InstalledAppFlow.from_client_secrets_file(ruta_credenciales, ALCANCE)
                credenciales = flujo.run_local_server(port=0)
            with open('token.pickle', 'wb') as token:
                pickle.dump(credenciales, token)
        return build('drive', 'v3', credentials=credenciales)

    def obtener_o_crear_carpeta(self, nombre, id_padre):
        consulta = f"name='{nombre}' and mimeType='application/vnd.google-apps.folder'"
        if id_padre:
            consulta += f" and '{id_padre}' in parents"
        respuesta = self.servicio.files().list(q=consulta, fields="files(id, name)").execute()
        archivos = respuesta.get('files', [])
        if archivos:
            return archivos[0]['id']
        else:
            metadatos = {'name': nombre, 'mimeType': 'application/vnd.google-apps.folder'}
            if id_padre:
                metadatos['parents'] = [id_padre]
            carpeta = self.servicio.files().create(body=metadatos, fields='id').execute()
            return carpeta.get('id')

    def subir_archivo(self, archivo, nombre_guardar):
        id_carpeta_destino = self.obtener_o_crear_carpeta("Archivos_Adjuntos", self.id_carpeta_raiz)
        ruta_temp = f"temp_{nombre_guardar}"
        archivo.save(ruta_temp)
        metadatos = {'name': nombre_guardar, 'parents': [id_carpeta_destino]}
        media = MediaFileUpload(ruta_temp, resumable=True)
        archivo_guardado = self.servicio.files().create(body=metadatos, media_body=media, fields='id').execute()
        os.remove(ruta_temp)
        return archivo_guardado.get('id')

    def descargar_archivo(self, id_archivo):
        solicitud = self.servicio.files().get_media(fileId=id_archivo)
        buffer = io.BytesIO()
        descargador = MediaIoBaseDownload(buffer, solicitud)
        hecho = False
        while not hecho:
            estado, hecho = descargador.next_chunk()
        buffer.seek(0)
        return buffer

    def guardar_datos_json(self, contenido):
        try:
            consulta = f"name='{ARCHIVO_DATOS_NUBE}' and '{self.id_carpeta_raiz}' in parents"
            respuesta = self.servicio.files().list(q=consulta, fields="files(id)").execute()
            for f in respuesta.get('files', []):
                self.servicio.files().delete(fileId=f['id']).execute()
            
            ruta_temp = "temp_datos.json"
            with open(ruta_temp, "w", encoding="utf-8") as f:
                json.dump(contenido, indent=4, ensure_ascii=False, fp=f)
            metadatos = {'name': ARCHIVO_DATOS_NUBE, 'parents': [self.id_carpeta_raiz]}
            media = MediaFileUpload(ruta_temp, mimetype='application/json')
            self.servicio.files().create(body=metadatos, media_body=media).execute()
            os.remove(ruta_temp)
        except Exception as e:
            flash(f"Error al guardar datos: {str(e)}", "danger")

    def cargar_datos_json(self):
        try:
            consulta = f"name='{ARCHIVO_DATOS_NUBE}' and '{self.id_carpeta_raiz}' in parents"
            respuesta = self.servicio.files().list(q=consulta, fields="files(id)").execute()
            archivos = respuesta.get('files', [])
            if not archivos:
                return []
            solicitud = self.servicio.files().get_media(fileId=archivos[0]['id'])
            buffer = io.BytesIO()
            descargador = MediaIoBaseDownload(buffer, solicitud)
            hecho = False
            while not hecho:
                estado, hecho = descargador.next_chunk()
            buffer.seek(0)
            return json.load(buffer)
        except Exception as e:
            flash(f"Error al cargar datos: {str(e)}", "danger")
            return []

# ---------------- INSTANCIA DE CONEXIÓN ----------------
drive = ConexionDrive()

# ---------------- RUTAS WEB ----------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('clave') == CLAVE_ACCESO:
            session['logueado'] = True
            return redirect(url_for('inicio'))
        flash("Clave incorrecta", "danger")
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>Inicio de Sesión</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body class="container mt-5">
        <div class="row justify-content-center">
            <div class="col-md-4">
                <h3 class="text-center">Acceso al Sistema</h3>
                {% with mensajes = get_flashed_messages(with_categories=true) %}
                    {% if mensajes %}
                        {% for categoria, mensaje in mensajes %}
                            <div class="alert alert-{{ categoria }} mt-2">{{ mensaje }}</div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}
                <form method="POST" class="mt-3">
                    <div class="mb-3">
                        <label>Clave de acceso:</label>
                        <input type="password" name="clave" class="form-control" required>
                    </div>
                    <button type="submit" class="btn btn-primary w-100">Entrar</button>
                </form>
            </div>
        </div>
    </body>
    </html>
    """)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
def inicio():
    if not session.get('logueado'):
        return redirect(url_for('login'))
    procesos = drive.cargar_datos_json()
    for p in procesos:
        if p.get("estado") == "vigente" and p.get("fecha_fin"):
            try:
                fecha_lim = datetime.strptime(p["fecha_fin"], "%d/%m/%Y")
                p["dias_restantes"] = calcular_dias_restantes(fecha_lim)
            except:
                p["dias_restantes"] = "—"
        else:
            p["dias_restantes"] = "—"
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>Gestión de Procesos</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body class="container-fluid mt-3">
        <div class="d-flex justify-content-between align-items-center mb-3">
            <h2>Gestión de Procesos - 90 días hábiles</h2>
            <a href="{{ url_for('logout') }}" class="btn btn-danger">Cerrar sesión</a>
        </div>

        {% with mensajes = get_flashed_messages(with_categories=true) %}
            {% if mensajes %}
                {% for categoria, mensaje in mensajes %}
                    <div class="alert alert-{{ categoria }}">{{ mensaje }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}

        <a href="{{ url_for('nuevo_proceso') }}" class="btn btn-success mb-3">+ Nuevo Proceso</a>

        <div class="table-responsive">
            <table class="table table-striped table-bordered">
                <thead class="table-dark">
                    <tr>
                        <th>Nombre</th>
                        <th>Cédula</th>
                        <th>N° Obligaciones</th>
                        <th>Inicio</th>
                        <th>Límite</th>
                        <th>Días restantes</th>
                        <th>Monto</th>
                        <th>Abonos</th>
                        <th>Estado</th>
                        <th>Archivos</th>
                        <th>Acciones</th>
                    </tr>
                </thead>
                <tbody>
                {% for p in procesos %}
                    <tr class="{{ 'table-warning' if p.estado == 'vigente' and p.dias_restantes <= 10 else 'table-light' if p.estado == 'vigente' else 'table-success' }}">
                        <td>{{ p.nombre }}</td>
                        <td>{{ p.cedula }}</td>
                        <td>{{ p.numeros_obligacion|join(', ') }}</td>
                        <td>{{ p.fecha_inicio }}</td>
                        <td>{{ p.fecha_fin }}</td>
                        <td>
                            {% if p.dias_restantes == '—' %}
                                —
                            {% elif p.dias_restantes < 0 %}
                                <span class="text-danger">Vencido hace {{ -p.dias_restantes }} días</span>
                            {% elif p.dias_restantes <= 10 %}
                                <span class="text-warning">Quedan {{ p.dias_restantes }}</span>
                            {% else %}
                                <span class="text-success">Quedan {{ p.dias_restantes }}</span>
                            {% endif %}
                        </td>
                        <td>${{ "%.2f"|format(p.monto) }}</td>
                        <td>${{ "%.2f"|format(p.abonos) }}</td>
                        <td>{{ p.estado }}</td>
                        <td>
                            <a href="{{ url_for('ver_archivos', cedula=p.cedula, nombre=p.nombre) }}" class="btn btn-sm btn-outline-info">Ver todos</a>
                        </td>
                        <td>
                            <a href="{{ url_for('editar', cedula=p.cedula, nombre=p.nombre) }}" class="btn btn-sm btn-primary">Editar</a>
                            <a href="{{ url_for('eliminar', cedula=p.cedula, nombre=p.nombre) }}" class="btn btn-sm btn-danger" onclick="return confirm('¿Eliminar este proceso?')">Eliminar</a>
                            {% if p.estado == 'vigente' %}
                                <a href="{{ url_for('marcar_terminado', cedula=p.cedula, nombre=p.nombre) }}" class="btn btn-sm btn-secondary">Terminado</a>
                            {% endif %}
                        </td>
                    </tr>
                {% else %}
                    <tr><td colspan="11" class="text-center">No hay procesos registrados</td></tr>
                {% endfor %}
                </tbody>
            </table>
        </div>
    </body>
    </html>
    """, procesos=procesos)

@app.route('/nuevo', methods=['GET', 'POST'])
def nuevo_proceso():
    if not session.get('logueado'):
        return redirect(url_for('login'))
    if request.method == 'POST':
        try:
            fecha_inicio = datetime.strptime(request.form.get('fecha_inicio'), "%d/%m/%Y")
            fecha_fin = sumar_dias_habiles(fecha_inicio, 90)
            
            numeros_obligacion = [n.strip() for n in request.form.getlist('numeros_obligacion') if n.strip()]
            numeros_obligacion = numeros_obligacion[:MAX_OBLIGACIONES]

            proceso = {
                "nombre": request.form.get('nombre'),
                "cedula": request.form.get('cedula'),
                "clave": request.form.get('clave', ''),
                "correo": request.form.get('correo', ''),
                "celular": request.form.get('celular', ''),
                "direccion": request.form.get('direccion', ''),
                "nombre_obligacion": request.form.get('nombre_obligacion', ''),
                "numeros_obligacion": numeros_obligacion,
                "observaciones": request.form.get('observaciones', ''),
                "fecha_inicio": fecha_inicio.strftime("%d/%m/%Y"),
                "fecha_fin": fecha_fin.strftime("%d/%m/%Y"),
                "monto": float(request.form.get('monto') or 0),
                "abonos": float(request.form.get('abonos') or 0),
                "estado": "vigente",
                "firma_id": "",
                "cedula_frente_id": "",
                "cedula_reverso_id": "",
                "pdf_ids": [],
                "videos_ids": [],
                "juez_ids": []
            }

            if request.files.get('firma') and request.files['firma'].filename:
                proceso['firma_id'] = drive.subir_archivo(request.files['firma'], f"firma_{datetime.now().strftime('%Y%m%d%H%M%S')}")
            
            if request.files.get('cedula_frente') and request.files['cedula_frente'].filename:
                proceso['cedula_frente_id'] = drive.subir_archivo(request.files['cedula_frente'], f"cedula_frente_{datetime.now().strftime('%Y%m%d%H%M%S')}")
            
            if request.files.get('cedula_reverso') and request.files['cedula_reverso'].filename:
                proceso['cedula_reverso_id'] = drive.subir_archivo(request.files['cedula_reverso'], f"cedula_reverso_{datetime.now().strftime('%Y%m%d%H%M%S')}")
            
            for pdf in request.files.getlist('pdf_respuestas'):
                if pdf.filename:
                    proceso['pdf_ids'].append(drive.subir_archivo(pdf, f"pdf_{datetime.now().strftime('%Y%m%d%H%M%S')}_{pdf.filename}"))
            
            for video in request.files.getlist('videos'):
                if video.filename:
                    proceso['videos_ids'].append(drive.subir_archivo(video, f"video_{datetime.now().strftime('%Y%m%d%H%M%S')}_{video.filename}"))
            
            for archivo in request.files.getlist('juez'):
                if archivo.filename:
                    proceso['juez_ids'].append(drive.subir_archivo(archivo, f"juez_{datetime.now().strftime('%Y%m%d%H%M%S')}_{archivo.filename}"))

            lista = drive.cargar_datos_json()
            lista.append(proceso)
            drive.guardar_datos_json(lista)
            flash("✅ Proceso guardado correctamente", "success")
            return redirect(url_for('inicio'))
        except Exception as e:
            flash(f"❌ Error: {str(e)}", "danger")

    campos_obligacion = ''.join([f'<input type="text" name="numeros_obligacion" class="form-control d-inline w-25 m-1" placeholder="N° {i+1}">' for i in range(MAX_OBLIGACIONES)])

    return render_template_string("""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>Nuevo Proceso</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body class="container mt-4">
        <h3>Registrar Nuevo Proceso</h3>
        <a href="{{ url_for('inicio') }}" class="btn btn-secondary mb-3">← Volver</a>
        {% with mensajes = get_flashed_messages(with_categories=true) %}
            {% if mensajes %}{% for c,m in mensajes %}<div class="alert alert-{{c}}">{{m}}</div>{% endfor %}{% endif %}
        {% endwith %}
        <form method="POST" enctype="multipart/form-data">
            <div class="row g-3">
                <div class="col-md-6">
                    <label>Nombre completo:</label>
                    <input type="text" name="nombre" class="form-control" required>
                </div>
                <div class="col-md-3">
                    <label>Cédula:</label>
                    <input type="text" name="cedula" class="form-control" required>
                </div>
                <div class="col-md-3">
                    <label>Clave:</label>
                    <input type="text" name="clave" class="form-control">
                </div>
                <div class="col-md-6">
                    <label>Correo:</label>
                    <input type="email" name="correo" class="form-control">
                </div>
                <div class="col-md-3">
                    <label>Celular:</label>
                    <input type="text" name="celular" class="form-control">
                </div>
                <div class="col-md-3">
                    <label>Fecha inicio (dd/mm/aaaa):</label>
                    <input type="text" name="fecha_inicio" class="form-control" placeholder="01/01/2026" required>
                </div>
                <div class="col-md-6">
                    <label>Dirección:</label>
                    <input type="text" name="direccion" class="form-control">
                </div>
                <div class="col-md-6">
                    <label>Nombre general de la obligación:</label>
                    <input type="text" name="nombre_obligacion" class="form-control">
                </div>

                <div class="col-md-12">
                    <label>Números de obligación (máximo 16):</label><br>
                    """ + campos_obligacion + """
                </div>

                <div class="col-md-4">
                    <label>Monto total ($):</label>
                    <input type="number" step="0.01" name="monto" class="form-control">
                </div>
                <div class="col-md-4">
                    <label>Abonos ($):</label>
                    <input type="number" step="0.01" name="abonos" class="form-control">
                </div>
                <div class="col-md-12">
                    <label>Observaciones:</label>
                    <textarea name="observaciones" class="form-control" rows="2"></textarea>
                </div>

                <div class="col-md-6">
                    <label>Firma:</label>
                    <input type="file" name="firma" class="form-control">
                </div>
                <div class="col-md-3">
                    <label>Cédula - Frente:</label>
                    <input type="file" name="cedula_frente" class="form-control">
                </div>
                <div class="col-md-3">
                    <label>Cédula - Reverso:</label>
                    <input type="file" name="cedula_reverso" class="form-control">
                </div>

                <div class="col-md-12">
                    <label>Respuestas en PDF (varios permitidos):</label>
                    <input type="file" name="pdf_respuestas" class="form-control" multiple accept=".pdf">
                </div>

                <div class="col-md-12">
                    <label>Videos (varios permitidos):</label>
                    <input type="file" name="videos" class="form-control" multiple accept="video/*">
                </div>

                <div class="col-md-12">
                    <label>Documentos del Juez (cualquier formato, varios):</label>
                    <input type="file" name="juez" class="form-control" multiple>
                </div>
            </div>
            <button type="submit" class="btn btn-primary mt-4">Guardar Proceso</button>
        </form>
    </body>
    </html>
    """)

@app.route('/editar', methods=['GET', 'POST'])
def editar():
    if not session.get('logueado'):
        return redirect(url_for('login'))
    cedula = request.args.get('cedula')
    nombre = request.args.get('nombre')
    lista = drive.cargar_datos_json()
    proceso = next((p for p in lista if p.get('cedula') == cedula and p.get('nombre') == nombre), None)
    if not proceso:
        flash("❌ Proceso no encontrado", "danger")
        return redirect(url_for('inicio'))
    
    if request.method == 'POST':
        try:
            fecha_inicio = datetime.strptime(request.form.get('fecha_inicio'), "%d/%m/%Y")
            fecha_fin = sumar_dias_habiles(fecha_inicio, 90)
            
            numeros_obligacion = [n.strip() for n in request.form.getlist('numeros_obligacion') if n.strip()]
            numeros_obligacion = numeros_obligacion[:MAX_OBLIGACIONES]

            proceso['nombre'] = request.form.get('nombre')
            proceso['cedula'] = request.form.get('cedula')
            proceso['clave'] = request.form.get('clave', '')
            proceso['correo'] = request.form.get('correo', '')
            proceso['celular'] = request.form.get('celular', '')
            proceso['direccion'] = request.form.get('direccion', '')
            proceso['nombre_obligacion'] = request.form.get('nombre_obligacion', '')
            proceso['numeros_obligacion'] = numeros_obligacion
            proceso['observaciones'] = request.form.get('observaciones', '')
            proceso['fecha_inicio'] = fecha_inicio.strftime("%d/%m/%Y")
            proceso['fecha_fin'] = fecha_fin.strftime("%d/%m/%Y")
            proceso['monto'] = float(request.form.get('monto') or 0)
            proceso['abonos'] = float(request.form.get('abonos') or 0)

            if request.files.get('firma') and request.files['firma'].filename:
                proceso['firma_id'] = drive.subir_archivo(request.files['firma'], f"firma_{datetime.now().strftime('%Y%m%d%H%M%S')}")
            
            if request.files.get('cedula_frente') and request.files['cedula_frente'].filename:
                proceso['cedula_frente_id'] = drive.subir_archivo(request.files['cedula_frente'], f"cedula_frente_{datetime.now().strftime('%Y%m%d%H%M%S')}")
            
            if request.files.get('cedula_reverso') and request.files['cedula_reverso'].filename:
                proceso['cedula_reverso_id'] = drive.subir_archivo(request.files['cedula_reverso'], f"cedula_reverso_{datetime.now().strftime('%Y%m%d%H%M%S')}")
            
            for pdf in request.files.getlist('pdf_respuestas'):
                if pdf.filename:
                    proceso['pdf_ids'].append(drive.subir_archivo(pdf, f"pdf_{datetime.now().strftime('%Y%m%d%H%M%S')}_{pdf.filename}"))
            
            for video in request.files.getlist('videos'):
                if video.filename:
                    proceso['videos_ids'].append(drive.subir_archivo(video, f"video_{datetime.now().strftime('%Y%m%d%H%M%S')}_{video.filename}"))
            
            for archivo in request.files.getlist('juez'):
                if archivo.filename:
                    proceso['juez_ids'].append(drive.subir_archivo(archivo, f"juez_{datetime.now().strftime('%Y%m%d%H%M%S')}_{archivo.filename}"))

            drive.guardar_datos_json(lista)
            flash("✅ Cambios guardados correctamente", "success")
            return redirect(url_for('inicio'))
        except Exception as e:
            flash(f"❌ Error: {str(e)}", "danger")

    campos_obligacion = ''.join([
        f'<input type="text" name="numeros_obligacion" class="form-control d-inline w-25 m-1" value="{proceso["numeros_obligacion"][i] if i < len(proceso.get("numeros_obligacion", [])) else ""}">'
        for i in range(MAX_OBLIGACIONES)
    ])

    return render_template_string("""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>Editar Proceso</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body class="container mt-4">
        <h3>Editar Proceso</h3>
        <a href="{{ url_for('inicio') }}" class="btn btn-secondary mb-3">← Volver</a>
        {% with mensajes = get_flashed_messages(with_categories=true) %}
            {% if mensajes %}{% for c,m in mensajes %}<div class="alert alert-{{c}}">{{m}}</div>{% endfor %}{% endif %}
        {% endwith %}
        <form method="POST" enctype="multipart/form-data">
            <div class="row g-3">
                <div class="col-md-6">
                    <label>Nombre completo:</label>
                    <input type="text" name="nombre" class="form-control" value="{{ proceso.nombre }}" required>
                </div>
                <div class="col-md-3">
                    <label>Cédula:</label>
                    <input type="text" name="cedula" class="form-control" value="{{ proceso.cedula }}" required>
                </div>
                <div class="col-md-3">
                    <label>Clave:</label>
                    <input type="text" name="clave" class="form-control" value="{{ proceso.clave }}">
                </div>
                <div class="col-md-6">
                    <label>Correo:</label>
                    <input type="email" name="correo" class="form-control" value="{{ proceso.correo }}">
                </div>
                <div class="col-md-3">
                    <label>Celular:</label>
                    <input type="text" name="celular" class="form-control" value="{{ proceso.celular }}">
                </div>
                <div class="col-md-3">
                    <label>Fecha inicio (dd/mm/aaaa):</label>
                    <input type="text" name="fecha_inicio" class="form-control" value="{{ proceso.fecha_inicio }}" required>
                </div>
                <div class="col-md-6">
                    <label>Dirección:</label>
                    <input type="text" name="direccion" class="form-control" value="{{ proceso.direccion }}">
                </div>
                <div class="col-md-6">
                    <label>Nombre general de la obligación:</label>
                    <input type="text" name="nombre_obligacion" class="form-control" value="{{ proceso.nombre_obligacion }}">
                </div>

                <div class="col-md-12">
                    <label>Números de obligación (máximo 16):</label><br>
                    """ + campos_obligacion + """
                </div>

                <div class="col-md-4">
                    <label>Monto total ($):</label>
                    <input type="number" step="0.01" name="monto" class="form-control" value="{{ proceso.monto }}">
                </div>
                <div class="col-md-4">
                    <label>Abonos ($):</label>
                    <input type="number" step="0.01" name="abonos" class="form-control" value="{{ proceso.abonos }}">
                </div>
                <div class="col-md-12">
                    <label>Observaciones:</label>
                    <textarea name="observaciones" class="form-control" rows="2">{{ proceso.observaciones }}</textarea>
                </div>

                <div class="col-md-6">
                    <label>Firma:</label>
                    <input type="file" name="firma" class="form-control">
                    {% if proceso.firma_id %}<small class="text-success">✅ Ya cargado</small>{% endif %}
                </div>
                <div class="col-md-3">
                    <label>Cédula - Frente:</label>
                    <input type="file" name="cedula_frente" class="form-control">
                    {% if proceso.cedula_frente_id %}<small class="text-success">✅ Ya cargado</small>{% endif %}
                </div>
                <div class="col-md-3">
                    <label>Cédula - Reverso:</label>
                    <input type="file" name="cedula_reverso" class="form-control">
                    {% if proceso.cedula_reverso_id %}<small class="text-success">✅ Ya cargado</small>{% endif %}
                </div>

                <div class="col-md-12">
                    <label>Agregar más PDF:</label>
                    <input type="file" name="pdf_respuestas" class="form-control" multiple accept=".pdf">
                    {% if proceso.pdf_ids %}<small class="text-success">✅ {{ proceso.pdf_ids|length }} archivos guardados</small>{% endif %}
                </div>

                <div class="col-md-12">
                    <label>Agregar más videos:</label>
                    <input type="file" name="videos" class="form-control" multiple accept="video/*">
                    {% if proceso.videos_ids %}<small class="text-success">✅ {{ proceso.videos_ids|length }} archivos guardados</small>{% endif %}
                </div>

                <div class="col-md-12">
                    <label>Agregar más documentos del Juez:</label>
                    <input type="file" name="juez" class="form-control" multiple>
                    {% if proceso.juez_ids %}<small class="text-success">✅ {{ proceso.juez_ids|length }} archivos guardados</small>{% endif %}
                </div>
            </div>
            <button type="submit" class="btn btn-primary mt-4">Guardar Cambios</button>
        </form>
    </body>
    </html>
    """, proceso=proceso)

@app.route('/ver_archivos')
def ver_archivos():
    if not session.get('logueado'):
        return redirect(url_for('login'))
    cedula = request.args.get('cedula')
    nombre = request.args.get('nombre')
    lista = drive.cargar_datos_json()
    proceso = next((p for p in lista if p.get('cedula') == cedula and p.get('nombre') == nombre), None)
    if not proceso:
        flash("❌ Proceso no encontrado", "danger")
        return redirect(url_for('inicio'))
    
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>Archivos del Proceso</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body class="container mt-4">
        <h3>📂 Archivos de: {{ proceso.nombre }} - Cédula: {{ proceso.cedula }}</h3>
        <a href="{{ url_for('inicio') }}" class="btn btn-secondary mb-4">← Volver al listado</a>

        {% if proceso.firma_id %}
        <div class="card mb-3">
            <div class="card-header bg-light"><strong>✍️ Firma</strong></div>
            <div class="card-body">
                <a href="{{ url_for('ver_archivo', archivo_id=proceso.firma_id) }}" target="_blank" class="btn btn-sm btn-outline-primary me-2">👁️ Ver</a>
                <a href="{{ url_for('descargar_archivo', archivo_id=proceso.firma_id, nombre='firma') }}" class="btn btn-sm btn-outline-secondary">⬇️ Descargar</a>
            </div>
        </div>
        {% endif %}

        {% if proceso.cedula_frente_id or proceso.cedula_reverso_id %}
        <div class="card mb-3">
            <div class="card-header bg-light"><strong>🆔 Cédula de Identidad</strong></div>
            <div class="card-body">
                {% if proceso.cedula_frente_id %}
                <p>Frente:
                    <a href="{{ url_for('ver_archivo', archivo_id=proceso.cedula_frente_id) }}" target="_blank" class="btn btn-sm btn-outline-primary me-2">👁️ Ver</a>
                    <a href="{{ url_for('descargar_archivo', archivo_id=proceso.cedula_frente_id, nombre='cedula_frente') }}" class="btn btn-sm btn-outline-secondary">⬇️ Descargar</a>
                </p>
                {% endif %}
                {% if proceso.cedula_reverso_id %}
                <p>Reverso:
                    <a href="{{ url_for('ver_archivo', archivo_id=proceso.cedula_reverso_id) }}" target="_blank" class="btn btn-sm btn-outline-primary me-2">👁️ Ver</a>
                    <a href="{{ url_for('descargar_archivo', archivo_id=proceso.cedula_reverso_id, nombre='cedula_reverso') }}" class="btn btn-sm btn-outline-secondary">⬇️ Descargar</a>
                </p>
                {% endif %}
            </div>
        </div>
        {% endif %}

        {% if proceso.pdf_ids %}
        <div class="card mb-3">
            <div class="card-header bg-light"><strong>📄 Documentos PDF</strong></div>
            <div class="card-body">
                {% set contador = 1 %}
                {% for aid in proceso.pdf_ids %}
                <p>Archivo PDF {{ contador }}:
                    <a href="{{ url_for('ver_archivo', archivo_id=aid) }}" target="_blank" class="btn btn-sm btn-outline-primary me-2">👁️ Ver</a>
                    <a href="{{ url_for('descargar_archivo', archivo_id=aid, nombre='pdf_'~contador) }}" class="btn btn-sm btn-outline-secondary">⬇️ Descargar</a>
                </p>
                {% set contador = contador + 1 %}
                {% endfor %}
            </div>
        </div>
        {% endif %}

        {% if proceso.videos_ids %}
        <div class="card mb-3">
            <div class="card-header bg-light"><strong>🎥 Videos</strong></div>
            <div class="card-body">
                {% set contador = 1 %}
                {% for aid in proceso.videos_ids %}
                <p>Video {{ contador }}:
                    <a href="{{ url_for('ver_archivo', archivo_id=aid) }}" target="_blank" class="btn btn-sm btn-outline-primary me-2">👁️ Ver</a>
                    <a href="{{ url_for('descargar_archivo', archivo_id=aid, nombre='video_'~contador) }}" class="btn btn-sm btn-outline-secondary">⬇️ Descargar</a>
                </p>
                {% set contador = contador + 1 %}
                {% endfor %}
            </div>
        </div>
        {% endif %}

        {% if proceso.juez_ids %}
        <div class="card mb-3">
            <div class="card-header bg-light"><strong>⚖️ Documentos del Juez</strong></div>
            <div class="card-body">
                {% set contador = 1 %}
                {% for aid in proceso.juez_ids %}
                <p>Archivo {{ contador }}:
                    <a href="{{ url_for('ver_archivo', archivo_id=aid) }}" target="_blank" class="btn btn-sm btn-outline-primary me-2">👁️ Ver</a>
                    <a href="{{ url_for('descargar_archivo', archivo_id=aid, nombre='juez_'~contador) }}" class="btn btn-sm btn-outline-secondary">⬇️ Descargar</a>
                </p>
                {% set contador = contador + 1 %}
                {% endfor %}
            </div>
        </div>
        {% endif %}

        {% if not proceso.firma_id and not proceso.cedula_frente_id and not proceso.cedula_reverso_id and not proceso.pdf_ids and not proceso.videos_ids and not proceso.juez_ids %}
        <div class="alert alert-info">Aún no hay archivos cargados en este proceso.</div>
        {% endif %}
    </body>
    </html>
    """, proceso=proceso)

@app.route('/ver_archivo/<archivo_id>')
def ver_archivo(archivo_id):
    if not session.get('logueado'):
        return redirect(url_for('login'))
    try:
        buffer = drive.descargar_archivo(archivo_id)
        return send_file(buffer, as_attachment=False)
    except Exception as e:
        flash(f"❌ No se pudo abrir el archivo: {str(e)}", "danger")
        return redirect(url_for('inicio'))

@app.route('/descargar_archivo/<archivo_id>')
def descargar_archivo(archivo_id):
    if not session.get('logueado'):
        return redirect(url_for('login'))
    nombre = request.args.get('nombre', 'archivo')
    try:
        buffer = drive.descargar_archivo(archivo_id)
        return send_file(buffer, download_name=f"{nombre}", as_attachment=True)
    except Exception as e:
        flash(f"❌ No se pudo descargar: {str(e)}", "danger")
        return redirect(url_for('inicio'))

@app.route('/eliminar')
def eliminar():
    if not session.get('logueado'):
        return redirect(url_for('login'))
    cedula = request.args.get('cedula')
    nombre = request.args.get('nombre')
    lista = drive.cargar_datos_json()
    lista = [p for p in lista if not (p.get('cedula') == cedula and p.get('nombre') == nombre)]
    drive.guardar_datos_json(lista)
    flash("✅ Proceso eliminado", "info")
    return redirect(url_for('inicio'))

@app.route('/marcar_terminado')
def marcar_terminado():
    if not session.get('logueado'):
        return redirect(url_for('login'))
    cedula = request.args.get('cedula')
    nombre = request.args.get('nombre')
    lista = drive.cargar_datos_json()
    for p in lista:
        if p.get('cedula') == cedula and p.get('nombre') == nombre:
            p['estado'] = "terminado"
            break
    drive.guardar_datos_json(lista)
    flash("✅ Proceso marcado como terminado", "success")
    return redirect(url_for('inicio'))

# ---------------- INICIO ADAPTADO PARA RENDER ----------------
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
