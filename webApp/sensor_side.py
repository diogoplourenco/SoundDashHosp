import json
import time
import paho.mqtt.client as mqtt
import os

CONFIG_FILE = "./config.json"
MQTT_BROKER = "localhost"
MQTT_PORT = 1881
SUBSCRIBE_TOPIC = "sensor1/update"
PUBLISH_TOPIC = "sensor1/config"

# Função para publicar configuração atual
def publicar_configuracao(client, config):
    payload = json.dumps(config)
    client.publish(PUBLISH_TOPIC, payload=payload, retain=True)
    print(f"📤 Configuração publicada no tópico '{PUBLISH_TOPIC}':\n{payload}")

# Callback: quando conecta
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ Ligado ao broker MQTT.")
        client.subscribe(SUBSCRIBE_TOPIC)
        print(f"📡 Subscrito ao tópico: {SUBSCRIBE_TOPIC}")
    else:
        print(f"❌ Erro ao conectar. Código: {rc}")

# Callback: quando recebe mensagem
def on_message(client, userdata, msg):
    try:
        payload_str = msg.payload.decode()
        dados = json.loads(payload_str)

        print(f"\n📥 Mensagem recebida:\n{json.dumps(dados, indent=2)}")

        # Salvar novo conteúdo no ficheiro
        with open(CONFIG_FILE, "w") as f:
            json.dump(dados, f, indent=2)
            
        if dados:
            publicar_configuracao(client, dados)
        else:
            print("⚠️ Dados recebidos inválidos (faltam campos 'sensor' ou 'config').")

    except Exception as e:
        print(f"❌ Erro ao processar mensagem: {e}")

def main():
    # Verifica se ficheiro existe
    if not os.path.exists(CONFIG_FILE):
        print(f"⚠️ Ficheiro '{CONFIG_FILE}' não encontrado.")
        return

    # Lê configuração inicial
    with open(CONFIG_FILE, "r") as f:
        try:
            dados = json.load(f)
        except Exception as e:
            print(f"❌ Erro ao ler o ficheiro: {e}")
            return

    if not dados:
        print("⚠️ Ficheiro inválido. Campos 'sensor' e 'config' são obrigatórios.")
        return

    # Configura o cliente MQTT
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(MQTT_BROKER, MQTT_PORT, 60)

    # Publica a configuração atual
    client.loop_start()
    time.sleep(1)  # Aguarda conexão antes de publicar
    publicar_configuracao(client, dados)

    # Aguarda mensagens
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Interrompido pelo utilizador.")
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()
