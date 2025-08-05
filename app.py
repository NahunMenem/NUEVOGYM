import textwrap
import pytz
import urllib3
import requests
from flask import Flask, json, render_template, request, jsonify
from requests.auth import HTTPDigestAuth
from flask import Flask, render_template, request, jsonify, redirect, url_for
import psycopg2


app = Flask(__name__)
from flask_sqlalchemy import SQLAlchemy

import os
DATABASE_URL = os.environ.get("DATABASE_URL")
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False




# Configuración del lector
HIKVISION_IP = "192.168.1.32"
USERNAME = "admin"
PASSWORD = "3804315721A"
BASE_URL = f"https://{HIKVISION_IP}/ISAPI"

# Desactivar advertencias por certificado autofirmado
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Modelo de base de datos para usuarios--------------------------------------------------------------------------------------------------------
class UsuarioLector(db.Model):
    __tablename__ = 'usuarios_lector'
    id = db.Column(db.Integer, primary_key=True)
    legajo = db.Column(db.String(20), unique=True, nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    genero = db.Column(db.String(20))
    fecha_nacimiento = db.Column(db.Date)
    telefono = db.Column(db.String(30))
    valido_hasta = db.Column(db.Date)

#DATABASE_URL = "postgresql://negocio2_user:0reioO9H1lLJqE2IazaFKoZ55ZItnU5X@dpg-d04do9qdbo4c73egutjg-a.oregon-postgres.render.com/negocio2"

@app.route('/cargar_usuario', methods=['POST'])
def cargar_usuario():
    data = request.json
    nombre = data.get("nombre")
    legajo = data.get("legajo")
    genero = data.get("genero")
    fecha_nacimiento = data.get("fecha_nacimiento")  # yyyy-mm-dd
    telefono = data.get("telefono")
    valido_hasta = data.get("valido_hasta") + " 00:00:00"

    payload = {
        "UserInfo": {
            "employeeNo": legajo,
            "name": nombre,
            "userType": "normal",
            "Valid": {
                "enable": True,
                "beginTime": "2024-01-01T00:00:00",
                "endTime": valido_hasta.replace(" ", "T")
            },
            "doorRight": "1"
        }
    }

    try:
        # Cargar usuario en el lector
        res = requests.post(
            f"{BASE_URL}/AccessControl/UserInfo/Record?format=json",
            json=payload,
            headers={"Content-Type": "application/json"},
            auth=HTTPDigestAuth(USERNAME, PASSWORD),
            verify=False
        )

        # Cargar o actualizar en la base de datos
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO usuarios_lector (nombre, legajo, genero, fecha_nacimiento, telefono, valido_hasta)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (legajo) DO UPDATE SET
              nombre = EXCLUDED.nombre,
              genero = EXCLUDED.genero,
              fecha_nacimiento = EXCLUDED.fecha_nacimiento,
              telefono = EXCLUDED.telefono,
              valido_hasta = EXCLUDED.valido_hasta
        """, (
            nombre,
            legajo,
            genero,
            fecha_nacimiento if fecha_nacimiento else None,
            telefono,
            valido_hasta
        ))
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({"status": res.status_code, "response": res.text})

    except Exception as e:
        return jsonify({"error": str(e)}), 500




@app.route('/formulario_usuario')
def formulario_usuario():
    return render_template('cargar_usuario.html')




# Ruta para listar usuarios-------------------------------------------------------------------------------------------
from datetime import date, timedelta, timezone

@app.route('/listar_usuarios')
def listar_usuarios():
    url = f"{BASE_URL}/AccessControl/UserInfo/Search?format=json"
    payload = {
        "UserInfoSearchCond": {
            "searchID": "1",
            "maxResults": 100,
            "searchResultPosition": 0
        }
    }

    try:
        # Datos del lector
        res = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            auth=HTTPDigestAuth(USERNAME, PASSWORD),
            verify=False
        )
        usuarios_lector = res.json().get("UserInfoSearch", {}).get("UserInfo", [])

        # Datos de la base
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("SELECT legajo, genero, fecha_nacimiento, telefono FROM usuarios_lector")
        datos_db = cur.fetchall()
        conn.close()

        # Diccionario rápido
        datos_dict = {
            fila[0]: {
                "genero": fila[1],
                "fecha_nacimiento": fila[2],
                "telefono": fila[3]
            }
            for fila in datos_db
        }

        # Fecha de hoy para evaluar membresía
        fecha_hoy = date.today().isoformat()

        # Fusión
        for u in usuarios_lector:
            legajo = u.get("employeeNo")
            datos_extra = datos_dict.get(legajo)
            if datos_extra:
                u["genero"] = datos_extra["genero"]
                u["fecha_nacimiento"] = datos_extra["fecha_nacimiento"]
                u["telefono"] = datos_extra["telefono"]
            else:
                u["genero"] = u["fecha_nacimiento"] = u["telefono"] = None

            # Evaluación de membresía
            if u.get("Valid") and "endTime" in u["Valid"]:
                fecha_validez = u["Valid"]["endTime"][:10]  # yyyy-mm-dd
                u["membresia"] = "Vigente" if fecha_validez >= fecha_hoy else "Vencido"
            else:
                u["membresia"] = "Sin datos"

        return render_template("lista_usuarios.html", usuarios=usuarios_lector)

    except Exception as e:
        return f"Error al obtener usuarios: {str(e)}"




@app.route('/eliminar_usuario/<string:employee_no>', methods=['POST'])
def eliminar_usuario(employee_no):
    url = f"{BASE_URL}/ISAPI/AccessControl/UserInfoDetail/Delete?format=json"
    payload = {
        "UserInfoDetail": {
            "employeeNo": employee_no
        }
    }

    try:
        res = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            auth=HTTPDigestAuth(USERNAME, PASSWORD),
            verify=False
        )
        print(f"Eliminado {employee_no}: {res.status_code} - {res.text}")
        return jsonify({"status": res.status_code, "response": res.text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500







# aca vamos a ver los logs de ingreso--------------------------------------------------------------------------------------------







# Ruta para editar un usuario existente-----------------------------------------------------------------------------------------
@app.route('/editar_usuario', methods=['POST'])
def editar_usuario():
    legajo = request.form['legajo_editar']
    nombre = request.form['nombre']
    genero = request.form.get('genero') or None
    fecha_nac = request.form.get('fecha_nacimiento') or None
    telefono = request.form.get('telefono') or None

    # Actualizar en la base de datos local
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("""
            UPDATE usuarios_lector
            SET genero = %s, fecha_nacimiento = %s, telefono = %s
            WHERE legajo = %s
        """, (genero, fecha_nac, telefono, legajo))
        conn.commit()
        conn.close()
    except Exception as e:
        return jsonify({"error": "Error actualizando en base de datos", "detalle": str(e)}), 500

    # Opcional: actualizar también en el lector (si querés cambiar nombre o algo)
    payload = {
        "UserInfo": {
            "employeeNo": legajo,
            "name": nombre,
            "userType": "normal",
            "Valid": {
                "enable": True,
                "beginTime": "2024-01-01T00:00:00",
                "endTime": "2030-01-01T00:00:00"  # Fecha arbitraria
            },
            "doorRight": "1"
        }
    }

    url = f"{BASE_URL}/AccessControl/UserInfo/Modify?format=json"

    try:
        res = requests.put(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            auth=HTTPDigestAuth(USERNAME, PASSWORD),
            verify=False
        )
        print("Editar usuario:", res.status_code, res.text)
        return redirect("/listar_usuarios")
    except Exception as e:
        return jsonify({"error": "Error actualizando en el lector", "detalle": str(e)}), 500




# Ruta para el dashboard de estadísticas------------------------------------------------------------------------------------------------------------------------------
from flask import request

@app.route('/dashboard')
def dashboard():
    from datetime import datetime
    fecha_desde = request.args.get('desde')
    fecha_hasta = request.args.get('hasta')

    condiciones = []
    valores = []

    if fecha_desde:
        condiciones.append("p.fecha >= %s")
        valores.append(fecha_desde)
    if fecha_hasta:
        condiciones.append("p.fecha <= %s")
        valores.append(fecha_hasta)

    where_clause = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM usuarios_lector")
    total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM usuarios_lector WHERE genero = 'Masculino'")
    hombres = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM usuarios_lector WHERE genero = 'Femenino'")
    mujeres = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM usuarios_lector WHERE genero NOT IN ('Masculino', 'Femenino') OR genero IS NULL")
    otros = cur.fetchone()[0]

    # Ingresos totales
    cur.execute(f"SELECT COALESCE(SUM(p.monto), 0) FROM pagos_lector p {where_clause}", valores)
    total_ingresos = cur.fetchone()[0]

    # Ingresos por método de pago
    cur.execute(f"""
        SELECT metodo_pago, SUM(monto)
        FROM pagos_lector p
        {where_clause}
        GROUP BY metodo_pago
    """, valores)
    ingresos_por_metodo = cur.fetchall()

    # Ingresos por cliente
    cur.execute(f"""
        SELECT u.nombre, SUM(p.monto)
        FROM pagos_lector p
        JOIN usuarios_lector u ON u.legajo = p.legajo
        {where_clause}
        GROUP BY u.nombre
        ORDER BY SUM(p.monto) DESC
    """, valores)
    ingresos_por_cliente = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        'dashboard.html',
        total=total,
        hombres=hombres,
        mujeres=mujeres,
        otros=otros,
        total_ingresos=total_ingresos,
        ingresos_por_metodo=ingresos_por_metodo,
        ingresos_por_cliente=ingresos_por_cliente,
        desde=fecha_desde,
        hasta=fecha_hasta
    )




# Ruta para registrar un pago de usuario-----------------------------------------------------------------------------------------
@app.route('/registrar_pago', methods=['POST'])
def registrar_pago():
    from datetime import datetime
    
    legajo = request.form.get('legajo_pago')
    nuevo_valido_hasta = request.form.get('nuevo_valido_hasta')
    monto = request.form.get('monto_pago')
    metodo_pago = request.form.get('metodo_pago')

    # Validar y formatear fecha
    try:
        fecha_valida = datetime.strptime(nuevo_valido_hasta, '%Y-%m-%d').date()
        fecha_iso = fecha_valida.strftime('%Y-%m-%dT23:59:59')
    except ValueError:
        return "Fecha inválida", 400

    try:
        # Actualizar en PostgreSQL
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        cur.execute("""
            UPDATE usuarios_lector SET valido_hasta = %s WHERE legajo = %s
        """, (fecha_valida, legajo))

        cur.execute("""
            INSERT INTO pagos_lector (legajo, monto, fecha, metodo_pago)
            VALUES (%s, %s, CURRENT_DATE, %s)
        """, (legajo, monto, metodo_pago))

        conn.commit()
        cur.close()
        conn.close()

    except Exception as e:
        return f"Error al guardar en base de datos: {e}", 500

    # Enviar al lector Hikvision
    payload = {
        "UserInfo": {
            "employeeNo": legajo,
            "Valid": {
                "enable": True,
                "beginTime": datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
                "endTime": fecha_iso
            }
        }
    }

    try:
        res = requests.put(
            f"{BASE_URL}/AccessControl/UserInfo/Modify?format=json",
            json=payload,
            headers={"Content-Type": "application/json"},
            auth=HTTPDigestAuth(USERNAME, PASSWORD),
            verify=False
        )

        if res.status_code != 200:
            return f"Error en el lector: {res.text}", 500

    except Exception as e:
        return f"No se pudo conectar con el lector: {e}", 500

    return redirect('/listar_usuarios')




# Ruta para ver transacciones de pagos-----------------------------------------------------------------------------------------
from flask import request, render_template
from datetime import datetime
import psycopg2

@app.route('/transacciones', methods=['GET'])
def ver_transacciones():
    fecha_desde = request.args.get('desde')
    fecha_hasta = request.args.get('hasta')

    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        # Consulta base
        query = """
            SELECT p.fecha, p.monto, p.metodo_pago, u.legajo, u.nombre
            FROM pagos_lector p
            JOIN usuarios_lector u ON p.legajo = u.legajo
        """
        params = []

        # Filtros por fecha si están
        if fecha_desde and fecha_hasta:
            query += " WHERE p.fecha BETWEEN %s AND %s"
            params.extend([fecha_desde, fecha_hasta])
        elif fecha_desde:
            query += " WHERE p.fecha >= %s"
            params.append(fecha_desde)
        elif fecha_hasta:
            query += " WHERE p.fecha <= %s"
            params.append(fecha_hasta)

        query += " ORDER BY p.fecha DESC"

        cur.execute(query, params)
        pagos_raw = cur.fetchall()

        # Convertir a lista de diccionarios
        pagos = [
            {
                "fecha": row[0],
                "monto": row[1],
                "metodo_pago": row[2],
                "legajo": row[3],
                "nombre": row[4]
            }
            for row in pagos_raw
        ]

        cur.close()
        conn.close()

        return render_template("transacciones.html", pagos=pagos, desde=fecha_desde, hasta=fecha_hasta)

    except Exception as e:
        return f"Error al cargar pagos: {e}", 500



from pytz import timezone
# Ruta para ver registros de ingreso-----------------------------------------------------------------------------------------
@app.route('/registros_ingreso')
def registros_ingreso():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("""
            SELECT legajo, nombre, fecha
            FROM ingresos_lector
            WHERE fecha::date = CURRENT_DATE
            ORDER BY fecha DESC
        """)
        logs = cur.fetchall()
        cur.close()
        conn.close()

        # Convertir a zona horaria de Argentina
        zona_arg = timezone('America/Argentina/Buenos_Aires')
        logs_arg = [(l, n, f.astimezone(zona_arg)) for l, n, f in logs]

        return render_template("registros_ingreso.html", logs=logs_arg)

    except Exception as e:
        return f"Error al obtener ingresos: {e}", 500




from flask import request, jsonify
from xml.etree import ElementTree as ET
from datetime import datetime
import psycopg2
from flask import Flask, request, jsonify

import traceback  # asegurate de tenerlo arriba
from pytz import timezone
from datetime import datetime
# Logs---------------------------------------------------------------------------------------------------
@app.route('/notificar_evento', methods=['POST'])
def notificar_evento():
    if 'event_log' in request.form:
        try:
            raw_json = request.form['event_log']
            data = json.loads(raw_json)

            evento = data.get('AccessControllerEvent', {})
            verify_mode = evento.get('currentVerifyMode')

            if verify_mode == 'faceOrFpOrCardOrPw':
                print("[ACCESO] Evento válido:", evento)

                legajo = evento.get('employeeNoString')
                nombre = evento.get('name')

                if legajo and nombre:
                    try:
                        # Obtener hora actual en zona horaria de Argentina
                        ahora_arg = datetime.now(timezone('America/Argentina/Buenos_Aires'))

                        conn = psycopg2.connect(DATABASE_URL)
                        cur = conn.cursor()
                        cur.execute("""
                            INSERT INTO ingresos_lector (legajo, nombre, fecha)
                            VALUES (%s, %s, %s)
                        """, (legajo, nombre, ahora_arg))

                        conn.commit()
                        cur.close()
                        conn.close()
                        print(f"[BD] Ingreso registrado: {nombre} ({legajo})")
                    except Exception as e:
                        print("[ERROR BD]", e)
                else:
                    print("[WARNING] Faltan datos: legajo o nombre")

            else:
                print("[IGNORADO] Evento no válido:", verify_mode)

            return '', 200
        except Exception as e:
            print("[ERROR] No se pudo procesar:", e)
            return '', 400
    else:
        print("[ERROR] No se recibió 'event_log'")
        return '', 400


@app.route('/pantalla_acceso')
def pantalla_acceso():
    return render_template("pantalla_acceso.html")

@app.route('/')
def inicio():
    return redirect(url_for('dashboard'))


from flask import jsonify
from datetime import datetime
from pytz import timezone

from flask import jsonify
from pytz import timezone
from datetime import datetime

@app.route('/api/ultimo_ingreso')
def api_ultimo_ingreso():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        cur.execute("""
            SELECT legajo, nombre, fecha
            FROM ingresos_lector
            ORDER BY fecha DESC
            LIMIT 1
        """)
        ingreso = cur.fetchone()

        if not ingreso:
            return jsonify({"estado": "esperando", "mensaje": "Esperando ingreso..."})

        legajo, nombre, fecha = ingreso

        # Traer fecha de vencimiento desde usuarios_lector
        cur.execute("SELECT valido_hasta FROM usuarios_lector WHERE legajo = %s", (legajo,))
        resultado = cur.fetchone()

        cur.close()
        conn.close()

        if not resultado:
            return jsonify({
                "estado": "incorrecto",
                "nombre": nombre,
                "mensaje": "Cliente no encontrado en sistema.",
                "fecha_vencimiento": None,
                "dias_restantes": 0,
                "legajo": legajo
            })

        valido_hasta = resultado[0]
        ahora = datetime.now(timezone('America/Argentina/Buenos_Aires')).date()

        dias_restantes = (valido_hasta - ahora).days
        fecha_str = valido_hasta.strftime('%Y-%m-%d')  # Para que JS lo entienda

        if valido_hasta >= ahora:
            return jsonify({
                "estado": "correcto",
                "nombre": nombre,
                "fecha_vencimiento": fecha_str,
                "dias_restantes": dias_restantes,
                "legajo": legajo
            })
        else:
            return jsonify({
                "estado": "incorrecto",
                "nombre": nombre,
                "fecha_vencimiento": fecha_str,
                "dias_restantes": dias_restantes,
                "legajo": legajo
            })

    except Exception as e:
        print("[API ERROR]", e)
        return jsonify({"estado": "error", "mensaje": str(e)}), 500



from flask import jsonify
from datetime import datetime
import psycopg2

@app.route('/api/cumples_mes')
def api_cumples_mes():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        hoy = datetime.now()
        mes_actual = hoy.month

        cur.execute("""
            SELECT nombre, TO_CHAR(fecha_nacimiento, 'DD/MM') as fecha
            FROM usuarios_lector
            WHERE EXTRACT(MONTH FROM fecha_nacimiento) = %s
            ORDER BY EXTRACT(DAY FROM fecha_nacimiento)
        """, (mes_actual,))
        resultados = cur.fetchall()

        cur.close()
        conn.close()

        lista = [{"nombre": r[0], "fecha": r[1]} for r in resultados]
        return jsonify(lista)

    except Exception as e:
        print("[ERROR CUMPLES]", e)
        return jsonify([]), 500

@app.route('/usuarios_inactivos')
def usuarios_inactivos():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        # Traer usuarios cuya última fecha de ingreso fue hace más de 60 días
        cur.execute("""
            SELECT u.legajo, u.nombre, u.genero, u.fecha_nacimiento, u.telefono, u.valido_hasta
            FROM usuarios_lector u
            LEFT JOIN (
                SELECT legajo, MAX(fecha) AS ultima_fecha
                FROM ingresos_lector
                GROUP BY legajo
            ) i ON u.legajo = i.legajo
            WHERE i.ultima_fecha IS NULL 
               OR i.ultima_fecha < CURRENT_DATE - INTERVAL '60 days'
            ORDER BY i.ultima_fecha NULLS FIRST;
        """)
        
        usuarios = []
        for row in cur.fetchall():
            usuarios.append({
                "employeeNo": row[0],
                "name": row[1],
                "genero": row[2],
                "fecha_nacimiento": row[3],
                "telefono": row[4],
                "valido_hasta": row[5],
                "membresia": "Vigente" if row[5] and row[5] >= date.today() else "Vencido"
            })

        cur.close()
        conn.close()

        return render_template("usuarios_inactivos.html", usuarios=usuarios)

    except Exception as e:
        return f"Error al obtener usuarios inactivos: {e}", 500

@app.route('/usuarios_sistema')
def usuarios_sistema():
    from datetime import date
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        cur.execute("""
            SELECT legajo, nombre, genero, fecha_nacimiento, telefono, valido_hasta
            FROM usuarios_lector
            ORDER BY nombre ASC
        """)
        datos = cur.fetchall()
        conn.close()

        usuarios = []
        for row in datos:
            usuarios.append({
                "legajo": row[0],
                "nombre": row[1],
                "genero": row[2],
                "fecha_nacimiento": row[3],
                "telefono": row[4],
                "valido_hasta": row[5],
                "membresia": "Vigente" if row[5] and row[5] >= date.today() else "Vencido"
            })

        return render_template("usuarios_sistema.html", usuarios=usuarios)

    except Exception as e:
        return f"Error al cargar usuarios del sistema: {e}", 500

@app.route('/eliminar_usuario_sistema/<string:legajo>', methods=['POST'])
def eliminar_usuario_sistema(legajo):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("DELETE FROM usuarios_lector WHERE legajo = %s", (legajo,))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "mensaje": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))


#if __name__ == '__main__':
 #   app.run(host="0.0.0.0", port=5000, debug=True)
