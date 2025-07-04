from influxdb_client import InfluxDBClient
from datetime import datetime, timedelta

# --- CONFIGURAÇÃO ---
INFLUX_URL = "http://localhost:8086"
INFLUX_TOKEN = "-ChZKEWHWyIIRKU6SRU2SvuupVlJGp1MHQywC4OTnSRy7r09Z2JM5pGmBN_hzb4-UCQ9MrxLY-UXqEnSRemLCg=="
ORG = "ISEL"
BUCKET = "Sensor_Data"
TEMPO_ANALISE = "10m"  # pode ser alterado conforme necessário

# --- CONECTAR AO INFLUX ---
client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=ORG)
query_api = client.query_api()

# --- QUERY FLUX ---
query = f'''
from(bucket: "{BUCKET}")
  |> range(start: -{TEMPO_ANALISE})
  |> filter(fn: (r) => 
    r["_measurement"] == "Audio" and
    (r["_field"] == "Evento" or r["_field"] == "sensor_id")
  )
  |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> filter(fn: (r) => r["Evento"] > 0)
  |> sort(columns: ["_time"])
'''

# --- EXECUTAR QUERY ---
tables = query_api.query(query)

# --- PARSE RESULTADOS ---
eventos = []
for table in tables:
    for row in table.records:
        eventos.append({
            "time": row.get_time(),
            "sensor": row.values.get("sensor_id"),
            "evento": row.values.get("Evento")
        })

# --- AGRUPAR EVENTOS CONTÍGUOS ---
intervalos = []
if eventos:
    inicio = eventos[0]["time"]
    fim = eventos[0]["time"]

    for i in range(1, len(eventos)):
        atual = eventos[i]["time"]
        anterior = eventos[i-1]["time"]
        delta = (atual - anterior).total_seconds()

        if delta <= 5:  # se o evento continuar até 5 segundos depois, ainda é o mesmo
            fim = atual
        else:
            intervalos.append((inicio, fim))
            inicio = atual
            fim = atual
    intervalos.append((inicio, fim))  # último evento

# --- RESULTADO FINAL ---
if intervalos:
    print("Eventos detectados nos seguintes intervalos:")
    for start, end in intervalos:
        duracao = end - start
        print(f"  - Início: {start} | Fim: {end} | Duração: {duracao}")
else:
    print("Nenhum evento detectado no intervalo escolhido.")

# --- ENCERRAR ---
client.close()
