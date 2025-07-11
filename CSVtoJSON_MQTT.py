import csv
import json
import time
import paho.mqtt.client as mqtt
import sys

def csv_to_json(file_path, sensor_name, mqtt_broker, mqtt_topic):
    client = mqtt.Client()
    client.connect(mqtt_broker, 1881, 60)
    
    with open(file_path, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            row["sensor_name"] = sensor_name  
            json_data = json.dumps(row)
            print(json_data)
            client.publish(mqtt_topic, json_data)
            time.sleep(1)  # Espera 3 segundos antes de processar a próxima linha

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: python CSVtoJSON_MQTT.py <caminho_do_arquivo_csv> <nome_do_sensor>")
        sys.exit(1)
    
    file_path = sys.argv[1]  # Obtém o caminho do arquivo CSV passado como argumento
    sensor_name = sys.argv[2]  # Obtém o nome do sensor passado como argumento
    mqtt_broker = "localhost"
    #mqtt_broker = "10.65.13.39"
    #mqtt_broker = "172.18.0.4"
    mqtt_topic = "csv/data"
    
    csv_to_json(file_path, sensor_name, mqtt_broker, mqtt_topic)
