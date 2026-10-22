# TecnoStore — Asistente de voz para una tienda técnica

Proyecto de Dialogflow ES que permite consultar pedidos y hacer preguntas sobre
cuatro fichas técnicas procesadas con OCR. La entrada y la salida de voz utilizan
el reconocimiento y la síntesis nativos de Dialogflow.

Los productos, los pedidos y las fichas PDF son datos de muestra para la práctica.

## Arquitectura

```text
Usuario (voz)
    ↕ STT / TTS nativos
Dialogflow ES (intenciones, entidades y contextos)
    ↓ webhook HTTPS
FastAPI
    ├── Consulta de pedidos → webhook/orders.json
    └── Preguntas documentales → texto OCR + prompt → Gemini
                                      ↑
                           data/knowledge_base.json
                                      ↑
                PDF → imágenes (Poppler) → OCR (Tesseract) → regex
```

El OCR se ejecuta previamente. El webhook utiliza su resultado durante la conversación.

## Intenciones y datos de conversación

| Intención | Función | Webhook |
|---|---|---|
| Default Welcome Intent | Bienvenida y presentación de las opciones. | No |
| Default Fallback Intent | Envía las preguntas no reconocidas a la consulta documental. | Sí |
| solicitar_estado_pedido | Recoge el código obligatorio, lo valida y consulta el pedido. | Sí, también durante slot filling |
| recibir_codigo_pedido | Recoge un nuevo código cuando queda un pedido pendiente de identificar. | Sí |
| confirmar_envio_si | Devuelve el número de seguimiento del pedido consultado. | Sí |
| confirmar_envio_no | Finaliza la confirmación sin facilitar el seguimiento. | Sí |
| consulta_documental | Responde preguntas usando las fichas procesadas por OCR. | Sí |
| horario_y_ubicacion | Responde con el horario y la dirección de la tienda de muestra. | No |
| despedida | Despedida. | No |

**Entidades:** `@codigo_pedido` es una entidad regex tolerante a mayúsculas y espacios;
`@producto` contiene router, SSD, monitor y teclado. El webhook normaliza el código
al formato `TEC-004521` y comprueba `TEC-[0-9]{6}` antes de buscarlo.

**Contextos:** `ctx_codigo_pendiente` conserva el estado de recogida o reintento del
código. `ctx_solicitud_en_curso` guarda el código encontrado para interpretar el
siguiente sí/no. El webhook cierra la confirmación después de responder.

## Archivos incluidos

```text
.env.example                        Configuración de ejemplo, sin claves reales
.gitignore                          Exclusiones de credenciales y archivos locales
README.md                           Caso de uso, arquitectura y ejecución
requirements.txt                    Dependencias de Python
Video demo.mp4                      Grabación de la demostración

dialogflow/
  build_agent_export.py             Definición y generación del agente
  tecnostore_agent.zip               Agente importable, sin URL ni credenciales de despliegue
ocr/
  generate_sample_docs.py           Generador de las cuatro fichas de muestra
  run_ocr.py                        OCR y extracción de campos mediante regex
  sample_docs/*.pdf                 Documentos utilizados en la práctica
data/
  knowledge_base.json               Texto OCR y campos extraídos
webhook/
  __init__.py                       Paquete Python del servicio
  main.py                           Endpoint de fulfillment y gestión de contextos
  business.py                       Normalización, regex y consulta de pedidos
  orders.json                       Pedidos simulados
  rag.py                            Preparación del contexto documental
  llm_client.py                     Cliente LLM y reglas de respuesta
```

## Decisiones técnicas

- **FastAPI como fulfillment:** Dialogflow gestiona la conversación y la voz; el
  webhook ejecuta la consulta de pedidos y la consulta documental.
- **OCR real:** los PDF se convierten en imágenes con Poppler y se reconocen con
  Tesseract. Las regex extraen referencia, precio, garantía en meses y fecha.
- **Contexto documental completo:** con cuatro fichas se puede enviar todo el texto
  OCR en el prompt, sin una base vectorial ni embeddings.
- **Respuesta fundamentada:** el prompt pide responder exclusivamente con el contexto
  y reconocer la ausencia de información. Esta instrucción reduce respuestas inventadas;
  debe comprobarse en la demostración con una pregunta fuera de los documentos.
- **Tiempo de respuesta:** la consulta documental tiene un límite de cuatro segundos
  para dejar margen dentro del tiempo de respuesta del webhook de Dialogflow ES.
- **Configuración local:** la clave del proveedor LLM se carga desde `.env`.
  El cliente implementa Gemini, Ollama y Groq; el ejemplo configura Gemini.

## Ejecución

### 1. Instalar dependencias y configurar el proveedor

Desde la raíz de una copia del repositorio, en PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Completar `GEMINI_API_KEY` en `.env` y usar un `GEMINI_MODEL` disponible para esa clave.
El archivo `.env` queda fuera de Git. La clave se obtiene en Google AI Studio.
Reiniciar el webhook después de cambiar la configuración.

### 2. Reproducir el OCR

Para este paso deben estar instalados Tesseract, el idioma español y Poppler.
Por ejemplo, en Ubuntu/WSL:

```bash
sudo apt-get install tesseract-ocr tesseract-ocr-spa poppler-utils
python -m pip install -r requirements.txt
python ocr/run_ocr.py --lang spa
```

En Windows, Tesseract y Poppler deben estar disponibles en `PATH` antes de ejecutar
el mismo script con el Python del entorno virtual.

Se incluyen las cuatro fichas en `ocr/sample_docs/` y el resultado en
`data/knowledge_base.json`; por tanto, no es necesario repetir el OCR para arrancar
la demo. Si se desea regenerar las fichas: `python ocr/generate_sample_docs.py`.
El OCR informa de los campos encontrados y de los que falten en cada documento.
Para utilizar documentos propios, crear `docs_raw/` y colocar allí los PDF o imágenes.

### 3. Arrancar el webhook

Desde la raíz del proyecto, en PowerShell:

```powershell
.\.venv\Scripts\python.exe -m uvicorn webhook.main:app --port 8000
```

`http://localhost:8000/health` debe devolver `{"status":"ok"}`.
En Linux/WSL se puede utilizar `python -m uvicorn webhook.main:app --port 8000`
desde un entorno con las dependencias instaladas.

### 4. Importar y conectar Dialogflow ES

1. Crear un agente de Dialogflow **ES**, con español (`es`) y zona horaria
   `Europe/Madrid`. Si el agente ya tiene otro idioma predeterminado, añadir español
   y seleccionarlo al editar y probar las intenciones.
2. En **Settings → Export and Import → Restore from ZIP**, importar
   `dialogflow/tecnostore_agent.zip`. La restauración reemplaza la configuración del agente.
3. Exponer el puerto 8000 mediante **VS Code → Ports → Forward a Port → 8000**.
   Para esta demo, seleccionar **Port Visibility → Public** y copiar la URL HTTPS.
4. En **Fulfillment**, habilitar Webhook y guardar esa URL terminada en `/webhook`.
   Con devtunnels, puede añadirse la cabecera `X-Tunnel-Skip-AntiPhishing-Page: true`.
   La URL del túnel puede cambiar y debe actualizarse cuando ocurra.
5. Verificar el webhook en los seis intents dinámicos de la tabla; en
   `solicitar_estado_pedido`, verificar también **Enable webhook call for slot filling**.
6. En **Settings → Speech**, habilitar **Automatic Text to Speech** y elegir voz española.
   En el simulador seleccionar `es` y utilizar el micrófono para probar la entrada de voz.

El ZIP incluido se genera desde el código y lleva el webhook desactivado hasta que
se configure una URL propia. Para regenerarlo desde la raíz del proyecto:

```powershell
.\.venv\Scripts\python.exe dialogflow/build_agent_export.py
```

También admite `--webhook-url https://TU-DOMINIO/webhook`. Los ajustes de voz se
configuran en la consola después de importar. El webhook y el túnel deben mantenerse
activos durante las pruebas.

## Conversación de demostración

Enviar o decir cada intervención por separado y esperar la respuesta:

| Usuario | Resultado esperado |
|---|---|
| Hola | Bienvenida. |
| Quiero saber el estado de mi pedido | Solicita el código de pedido. |
| TEC cero cero cuatro cinco dos uno | Identifica `TEC-004521`, informa de «en reparto» y pregunta por el seguimiento. |
| Sí | Facilita el seguimiento de SEUR y cierra el contexto. |
| ¿Qué garantía tiene el SSD Nova? | Responde 60 meses a partir del texto OCR. |
| ¿Cuánto cuesta un coche? | Indica que no dispone de esa información en los documentos. |

Repetir el flujo con «no» permite comprobar la otra rama de confirmación.
Los fallos de configuración o del proveedor LLM se comunican mediante una respuesta
hablada de indisponibilidad; esa respuesta no sustituye la prueba documental correcta.

## Entrega

Este repositorio contiene el código, las fichas, el resultado OCR, el README y un
agente importable generado desde su definición. Para conservar la configuración
probada en la consola, descargar también el export final desde Dialogflow ES y
revisarlo antes de compartirlo.

**Vídeo incluido:** [Ver Video demo.mp4](Video%20demo.mp4), de 1 minuto y 12 segundos.
La grabación muestra el saludo, la recogida del código y la confirmación del seguimiento
en el simulador, con entrada escrita y reproducción de las respuestas de audio.

Para completar la evidencia indicada en la guía de la práctica, falta mostrar la entrada
mediante micrófono y una pregunta resuelta a partir de los documentos. La demostración
final debe durar como máximo tres minutos y capturar el micrófono y el audio del sistema.

Las claves, las cuentas de servicio, los entornos virtuales, los logs y los paquetes
de entrega permanecen fuera del repositorio. El ZIP del agente incluido no contiene
credenciales ni una URL de despliegue personal.
