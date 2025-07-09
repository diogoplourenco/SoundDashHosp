from flask import Flask, request, jsonify, render_template, Response, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, UserMixin, current_user
from influxdb_client import InfluxDBClient
from datetime import datetime, timezone
from collections import defaultdict
from io import StringIO
import csv
import threading
import json
from werkzeug.security import check_password_hash
import paho.mqtt.publish as publish
import paho.mqtt.client as mqtt

mensagem_recebida = None
mensagem_evento = threading.Event()

app = Flask(__name__, template_folder='templates')
app.secret_key = 'uma_chave_muito_secreta'  # muda para algo mais seguro


MQTT_BROKER = 'localhost'
MQTT_PORT = 1881
# Configurações do InfluxDB
url = "http://localhost:8086"
token = "-ChZKEWHWyIIRKU6SRU2SvuupVlJGp1MHQywC4OTnSRy7r09Z2JM5pGmBN_hzb4-UCQ9MrxLY-UXqEnSRemLCg=="
org = "ISEL"
bucket = "Sensor_Data"
# --- Flask-Login setup ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # rota para login se não autenticado

def load_users():
    with open('users.json') as f:
        return json.load(f)

class User(UserMixin):
    def __init__(self, username):
        self.id = username

@login_manager.user_loader
def load_user(user_id):
    users = load_users()
    if user_id in users:
        return User(user_id)
    return None

# --- Rotas Auth ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        users = load_users()
        username = request.form.get('username')
        password = request.form.get('password')
        remember = request.form.get('remember') == 'on'
        if username in users and check_password_hash(users[username]['password'], password):
            user = User(username)
            login_user(user, remember=remember)
            flash('Login efetuado com sucesso!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('controlo'))
        else:
            flash('Credenciais inválidas.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Sessão terminada.', 'info')
    return redirect(url_for('homepage'))

# --- Rota protegida para o painel técnico ---

@app.route('/controlo')
@login_required
def controlo():
    return render_template('controlo.html', username=current_user.id)

# --- As tuas rotas originais ---
@app.route("/api/eventos")
def obter_dados_brutos():
    sensor = request.args.get("sensor")
    start_raw = request.args.get("start")
    end_raw = request.args.get("end")
    
    if not sensor:
        return jsonify({"erro": "Sensor não especificado"}), 400
    
    if not start_raw or not end_raw:
        return jsonify({"erro": "Parâmetros 'start' e 'end' são obrigatórios"}), 400

    # Converter para formato RFC3339 aceito pelo InfluxDB
    try:
        start_dt = datetime.strptime(start_raw, "%Y-%m-%dT%H:%M")
        end_dt = datetime.strptime(end_raw, "%Y-%m-%dT%H:%M")
        start = start_dt.isoformat() + "Z"
        end = end_dt.isoformat() + "Z"
    except ValueError as e:
        return jsonify({"erro": f"Formato inválido de data. Use YYYY-MM-DDTHH:MM. Detalhes: {str(e)}"}), 400

    # Campos a buscar
    fields = ['EventDetect'] + [f'EventType{i}' for i in range(1, 11)]
    field_filter = " or ".join([f'r["_field"] == "{f}"' for f in fields])

    query = f'''
    from(bucket: "{bucket}")
      |> range(start: {start}, stop: {end})
      |> filter(fn: (r) => r["_measurement"] == "{sensor}" and ({field_filter}))
      |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
      |> filter(fn: (r) => r["EventDetect"] > 0)
      |> sort(columns: ["_time"])
    '''

    try:
        client = InfluxDBClient(url=url, token=token, org=org)
        query_api = client.query_api()
        tables = query_api.query(query)
    except Exception as e:
        return jsonify({"erro": f"Erro ao consultar o InfluxDB: {str(e)}"}), 500

    dados = []
    for table in tables:
        for row in table.records:
            valores = row.values
            registro = {
                "time": row.get_time().isoformat(),
                "sensor": valores.get("sensor_id"),
                "EventDetect": valores.get("EventDetect"),
            }
            for i in range(1, 11):
                registro[f"EventType{i}"] = valores.get(f"EventType{i}", 0)
            dados.append(registro)
    return jsonify(dados)


@app.route("/api/stats")
def get_raw_data():
    start = request.args.get("start")
    end = request.args.get("end")
    measurement = request.args.get("sensor_id")  # <- novo
    if not start or not end or not measurement:
        return jsonify({"error": "Parâmetros 'start' , 'end' e 'measurement' são obrigatórios."}), 400
    try:
        datetime.fromisoformat(start.replace("Z", "+00:00"))
        datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError:
        return jsonify({"error": "Formato de data inválido."}), 400
    client = InfluxDBClient(url=url, token=token, org=org)
    query_api = client.query_api()

    query_laea = f'''
    from(bucket: "{bucket}")
      |> range(start: time(v: "{start}"), stop: time(v: "{end}"))
      |> filter(fn: (r) => r["_measurement"] == "{measurement}")
      |> filter(fn: (r) => r["_field"] == "LAEA")
    '''
    tables_laea = query_api.query(query_laea, org=org)
    laea = [{"time": record.get_time().isoformat(), "value": record.get_value()}
            for table in tables_laea for record in table.records if record.get_value() is not None]

    query_lcpeak = f'''
    from(bucket: "{bucket}")
      |> range(start: time(v: "{start}"), stop: time(v: "{end}"))
      |> filter(fn: (r) => r["_measurement"] == "{measurement}")
      |> filter(fn: (r) => r["_field"] == "LCpeak")
    '''
    tables_lcpeak = query_api.query(query_lcpeak, org=org)
    lcpeak = [{"time": record.get_time().isoformat(), "value": record.get_value()}
              for table in tables_lcpeak for record in table.records if record.get_value() is not None]
    return jsonify({
        "laea": laea,
        "lcpeak": lcpeak
    })

@app.route("/api/download")
def download_csv():
    start = request.args.get("start")
    end = request.args.get("end")
    measurement = request.args.get("sensor_id")
    if not start or not end or not measurement:
        return jsonify({"error": "Parâmetros 'start' , 'end' e 'measurement' são obrigatórios."}), 400
    try:
        datetime.fromisoformat(start.replace("Z", "+00:00"))
        datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError:
        return jsonify({"error": "Formato de data inválido."}), 400

    client = InfluxDBClient(url=url, token=token, org=org)
    query_api = client.query_api()

    query = f'''
    from(bucket: "{bucket}")
      |> range(start: time(v: "{start}"), stop: time(v: "{end}"))
      |> filter(fn: (r) => r["_measurement"] == "{measurement}")
    '''
    tables = query_api.query(query, org=org)

    data_by_time = defaultdict(dict)
    fields = set()

    for table in tables:
        for record in table.records:
            timestamp = record.get_time().isoformat()
            field = record.get_field()
            value = record.get_value()
            data_by_time[timestamp][field] = value
            fields.add(field)

    fields = list(fields)

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["timestamp"] + fields)

    for timestamp in sorted(data_by_time.keys()):
        row = [timestamp] + [data_by_time[timestamp].get(f, "") for f in fields]
        writer.writerow(row)

    output.seek(0)
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=SoundData_{start}_{end}.csv"}
    )
    
    
@app.route('/api/parametros', methods=['POST'])
def receber_parametros():
    try:
        req = request.get_json()
        sensor = req.get("sensor")
        config = req.get("config")

        if not sensor or not config:
            return jsonify({'erro': 'Parâmetros ausentes'}), 400

        topic = f"{sensor}/update"
        payload = json.dumps(config)
        print(f'Mensagem publicada em: {topic}\n')
        print(f'{payload}\n')
        publish.single(
            topic=topic,
            payload=payload,
            hostname=MQTT_BROKER,
            port=MQTT_PORT
        )

        return jsonify({'mensagem': f'Parâmetros enviados para {topic}'}), 200

    except Exception as e:
        print(f"[ERRO] {e}")
        return jsonify({'erro': 'Erro interno ao processar os dados'}), 500

    
@app.route('/')
def home():
    return render_template('homepage.html')

@app.route('/atual')
def atual():
    return render_template('atual.html')

@app.route('/tempo')
def tempo():
    return render_template('tempo.html')

@app.route('/mapa')
def mapa():
    return render_template('mapa.html')

@app.route('/display')
def display():
    return render_template('display.html')

@app.route('/eventos')
def eventos():
    return render_template('eventos.html')

@app.route('/guia')
def guia():
    return render_template('guia.html')


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
