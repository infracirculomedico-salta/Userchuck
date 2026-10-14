# WhatsApp Business — Círculo Médico de Salta

Sistema de comunicaciones por WhatsApp. Tiene dos partes independientes:

- **`sender/`** — manda mensajes de plantilla a los socios, a partir de un CSV.
  Se ejecuta a mano cuando hace falta.
- **`webhook/`** — recibe lo que pasa del otro lado (mensajes que escriben los
  socios, confirmaciones de entrega y lectura) y lo guarda en Oracle. Corre
  todo el tiempo como servicio.

No se necesitan las dos para usar una: se puede enviar aunque el webhook esté
caído, y el webhook sigue registrando aunque nadie envíe nada.

---

## Enviar mensajes

### 1. Ver qué plantillas hay

```bash
/opt/userchuck/venv311/bin/python /opt/userchuck/sender/main.py --listar
```

Las seis plantillas aprobadas, y las variables que lleva cada una:

| Plantilla | Variables | Para qué |
|---|---|---|
| `notificacion_liquidacion` | `nombre`, `periodo`, `monto` | Avisar que la liquidación de un período está disponible |
| `confirmacion_recepcion_solicitud` | `nombre`, `tramite` | Confirmar que se recibió una solicitud |
| `solicitud_documentacion` | `nombre`, `tramite`, `documentacion` | Pedir la documentación que falta |
| `aviso_suspension_prestacion` | `nombre` | Informar que una prestación tiene disponibilidad limitada |
| `aviso_institucional_general` | `nombre`, `detalle_aviso` | Aviso institucional, el texto va en `detalle_aviso` |
| `bienvenida_menu_principal` | *(ninguna)* | Presentación del canal |

El texto de cada mensaje está fijado en Meta y no se puede cambiar desde acá:
lo único que varía son las variables.

### 2. El archivo de contactos

**Todos los CSV de contactos van en la carpeta `/opt/userchuck/contactos/`.**
Siempre ahí, sin subcarpetas. Por ejemplo:

```
/opt/userchuck/contactos/Consentimientos_Wpp.csv
/opt/userchuck/contactos/liquidaciones_agosto.csv
```

Consejos para el nombre del archivo:

- Sin espacios ni acentos: `liquidaciones_agosto.csv`, no `Liquidaciones de Agosto.csv`.
- Que termine en `.csv`.
- Si vas a reemplazar un archivo viejo, podés pisarlo con el mismo nombre.

En los comandos, **`--archivo` lleva solo el nombre del archivo**: el sistema
lo busca en esa carpeta. Se puede escribir con o sin el `.csv`
(`--archivo liquidaciones_agosto` también anda). De un envío a otro lo único
que cambia es el nombre del archivo y la plantilla; el resto se copia y pega
tal cual.

Si el archivo no está, el sistema avisa y muestra la lista de los CSV que sí
hay en la carpeta, para que veas cómo se llama exactamente.

El CSV tiene que tener estas columnas, con estos nombres exactos:

```
FECHA;MAIL;APEYNOM;DNI;MATRICULA;WHATSAPP;ESTADO_CONSENTIMIENTO
14/8/2026;jperez@ejemplo.com;PEREZ JUAN CARLOS;12345678;9999;3875550101;ACEPTO
```

- **Solo se le manda a quien tiene `ACEPTO`** en `ESTADO_CONSENTIMIENTO`.
  Cualquier otro valor queda afuera.
- El separador puede ser `;`, tabulación o coma: se detecta solo.
- El encoding también se detecta (UTF-8 o latin-1). Si los acentos están mal
  guardados en el archivo, avisa antes de enviar.
- Los teléfonos pueden venir como `3875550101`, `03875550101`,
  `0387 15 5550101` o `+5493875550101`: todos se entienden.
- Puede tener columnas de más (`MONTO`, `PERIODO`...) para usarlas como
  variables.

### 3. De dónde sale cada variable

Cada variable de la plantilla necesita un origen:

- `--col variable=COLUMNA` → el valor sale de esa columna del CSV, distinto
  para cada socio.
- `--valor variable=texto` → el mismo texto para todo el envío.

`nombre` sale de la columna `APEYNOM` sin necesidad de indicarlo.

> Todos los comandos de este manual funcionan desde cualquier lugar: no hace
> falta moverse de carpeta con `cd`.

### 4. Simular primero. Siempre.

`--simular` arma todos los mensajes, valida todo y **no manda nada**. No
consume mensajes ni le llega nada a nadie.

```bash
/opt/userchuck/venv311/bin/python /opt/userchuck/sender/main.py \
    --archivo Consentimientos_Wpp.csv \
    --plantilla aviso_suspension_prestacion \
    --simular
```

Muestra a cuántos se le va a mandar, cuántos quedan afuera y por qué, y cómo
queda el primer mensaje:

```
=== Resumen de envío ===
Plantilla: aviso_suspension_prestacion (MARKETING, es_AR)
Contactos con consentimiento (ACEPTO): 431
Excluidos por NO ACEPTO: 7
Números inválidos: 3
Se van a enviar: 428
Primer mensaje: +5493875550101 -> {'nombre': 'Juan Carlos Perez'}
```

Revisá ese resumen antes de seguir. Si algo no cierra, todavía no salió nada.

### 5. Enviar

El mismo comando sin `--simular`:

```bash
/opt/userchuck/venv311/bin/python /opt/userchuck/sender/main.py \
    --archivo Consentimientos_Wpp.csv \
    --plantilla aviso_suspension_prestacion
```

Muestra el resumen y pregunta `¿Confirmás el envío? (s/n)`. Recién ahí sale.

### Ejemplos completos

Liquidaciones, con el monto de una columna del CSV y el período fijo:

```bash
/opt/userchuck/venv311/bin/python /opt/userchuck/sender/main.py \
    --archivo liquidaciones_agosto.csv \
    --plantilla notificacion_liquidacion \
    --col monto=MONTO \
    --valor periodo="agosto 2026"
```

Pedido de documentación, todo igual para todos:

```bash
/opt/userchuck/venv311/bin/python /opt/userchuck/sender/main.py \
    --archivo pendientes.csv \
    --plantilla solicitud_documentacion \
    --valor tramite="reempadronamiento" \
    --valor documentacion="DNI y matrícula profesional"
```

Bienvenida, que no lleva variables:

```bash
/opt/userchuck/venv311/bin/python /opt/userchuck/sender/main.py \
    --archivo Consentimientos_Wpp.csv \
    --plantilla bienvenida_menu_principal
```

### Retomar un envío cortado

Cada envío deja un log en `/opt/userchuck/sender/logs/envio_<fecha>_<hora>.csv`,
que **se escribe mensaje por mensaje**: si el proceso se corta, lo ya enviado queda
registrado igual.

Para seguir donde quedó, sin mandarle dos veces a nadie:

```bash
/opt/userchuck/venv311/bin/python /opt/userchuck/sender/main.py \
    --archivo Consentimientos_Wpp.csv \
    --plantilla aviso_suspension_prestacion \
    --reanudar /opt/userchuck/sender/logs/envio_20260917_154959.csv
```

Tiene que ser el mismo CSV de `/opt/userchuck/contactos/` y la misma
plantilla que el envío original. Si el envío se corta o hubo errores, al
final el sistema muestra `--reanudar` con la ruta del log que hay que usar:
copiala de ahí.

Omite a los que ya figuran con `OK` y reintenta a los que fallaron. Si el log
es de otra plantilla, se niega a seguir.

### El log de cada envío

```
plantilla,nombre,numero_original,numero_normalizado,resultado,detalle
notificacion_liquidacion,PEREZ JUAN CARLOS,3875550101,+5493875550101,OK,wamid.HBgNNTQ5...
```

| `resultado` | Qué pasó |
|---|---|
| `OK` | Meta lo aceptó. `detalle` es el id del mensaje |
| `ERROR` | No salió. `detalle` dice por qué |
| `OMITIDO` | Ya había recibido el mensaje (viene de `--reanudar`) |

Que diga `OK` significa que Meta lo aceptó, no que el socio lo haya leído. Eso
se ve en la base, con `ver_logs.py`.

### Todas las opciones

| Opción | Para qué |
|---|---|
| `--listar` | Muestra las plantillas y termina |
| `--archivo` | El nombre del CSV de contactos (se busca en `/opt/userchuck/contactos/`) |
| `--plantilla` | Cuál mandar |
| `--col var=COLUMNA` | La variable sale de una columna del CSV |
| `--valor var=texto` | La variable es fija para todo el envío |
| `--simular` | Valida todo sin enviar |
| `--reanudar LOG.csv` | Retoma un envío anterior (log en `/opt/userchuck/sender/logs/`) |
| `--pausa SEGUNDOS` | Espera entre mensajes (por defecto `0.2`) |
| `--modo cron` | No pregunta nada. Solo para tareas programadas |
| `--sin-verificar` | No consulta a Meta el estado de la plantilla |
| `--idioma` | Fuerza otro idioma. No hace falta tocarlo |

---

## El webhook

Recibe de Meta todo lo que pasa con los mensajes y lo guarda en dos tablas de
Oracle: `wsp_raw_inbox` (el dato crudo, como llegó) y `wsp_log_mensajes` (ya
procesado).

Corre como servicio: arranca solo al prender el servidor y se reinicia solo si
se cae.

```bash
sudo systemctl status cms-webhook      # cómo está
sudo systemctl restart cms-webhook     # reiniciarlo
journalctl -u cms-webhook -f           # ver qué está haciendo, en vivo
```

Tiene que decir `active (running)`.

### Ver lo que llegó

```bash
/opt/userchuck/venv311/bin/python /opt/userchuck/ver_logs.py              # últimos 20 mensajes
/opt/userchuck/venv311/bin/python /opt/userchuck/ver_logs.py -n 50        # últimos 50
/opt/userchuck/venv311/bin/python /opt/userchuck/ver_logs.py --entrantes  # solo lo que escriben los socios
/opt/userchuck/venv311/bin/python /opt/userchuck/ver_logs.py --salientes  # confirmaciones de lo que mandamos
/opt/userchuck/venv311/bin/python /opt/userchuck/ver_logs.py --raw        # el dato crudo de Meta
```

Los estados que puede tener un mensaje que enviamos: `sent` (Meta lo tomó),
`delivered` (llegó al teléfono), `read` (lo abrieron), `failed` (no se pudo
entregar).

---

## Límite de mensajes

La cuenta puede iniciar **250 conversaciones cada 24 horas** (período continuo,
no por día calendario: si mandás hoy a las 15:00, el cupo se libera mañana a
las 15:00).

Con más de 250 socios, los que exceden el límite fallan con error de Meta.
Quedan como `ERROR` en el log y se mandan al día siguiente con `--reanudar`.

El límite sube a 2.000 cuando se acumulan suficientes conversaciones de buena
calidad. Se mira en WhatsApp Manager → Información general → Límites de
mensajes.

---

## Cuando algo sale mal

**"No se encontró 'X' en /opt/userchuck/contactos"**
El archivo no está en la carpeta o el nombre está mal escrito (mayúsculas y
minúsculas cuentan). Abajo del error aparece la lista de los CSV que hay:
copiá el nombre de ahí.

**"Faltan columnas esperadas en el CSV"**
Los nombres de las columnas no son los correctos. Tienen que ser exactamente
los siete de arriba, en mayúsculas.

**"Estas columnas mapeadas con --col no existen en el CSV"**
Escribiste mal el nombre de una columna en `--col`. Corta antes de enviar, no
sale nada.

**"Faltan orígenes para estas variables"**
A la plantilla le falta indicarle de dónde sale alguna variable. Agregá el
`--col` o el `--valor` que falta.

**"La plantilla está en estado X en Meta, no APPROVED"**
Meta pausó o rechazó esa plantilla. Hasta que la vuelva a aprobar no se puede
usar.

**"Número inválido"** en el log
El teléfono del CSV no se pudo interpretar. El detalle dice por qué. Ese socio
no recibió nada: hay que corregir el número en el padrón.

**Muchos errores de límite al final de un envío grande**
Se llegó a las 250 conversaciones de las 24 horas. Es esperable. Al día
siguiente, `--reanudar` con el log de ese envío.

---

## Mantenimiento

**Si se crea o se modifica una plantilla en Meta**, hay que anotarla en
`sender/plantillas.py`: nombre, id, idioma, categoría, formato de parámetros y
variables. El sistema no acepta plantillas que no estén ahí, y antes de cada
envío verifica contra Meta que lo anotado coincida. Si no coincide, avisa.

**Las credenciales** están en `config/` y `sender/config/`, en archivos `.env`.
No se versionan ni se comparten.

**Los logs de envío** se acumulan en `/opt/userchuck/sender/logs/`. No se borran solos: son el
registro de qué se mandó y a quién.

---

## El asistente: enviar sin escribir comandos

1. Copiá el CSV de contactos a la carpeta `/opt/userchuck/contactos/`
   (ver [El archivo de contactos](#2-el-archivo-de-contactos)).
2. Escribí esto en la terminal y apretá Enter:

   ```bash
   /opt/userchuck/enviar
   ```

3. Contestá las preguntas escribiendo el número de la opción:
   - qué archivo de contactos usar,
   - qué mensaje mandar,
   - y, si el mensaje lo necesita, el valor de cada variable (por ejemplo
     el período). Si el CSV tiene columnas de más, como `MONTO`, te deja
     elegir sacar el valor de ahí.

4. **Siempre hace una simulación primero**: muestra a cuántos se les va a
   mandar y cómo queda el primer mensaje, sin mandar nada.
5. Si todo está bien, escribí `SI` para enviar de verdad. Cualquier otra
   respuesta cancela y no sale nada. Después te pide una última
   confirmación (`s/n`).

Para salir en cualquier momento sin enviar nada: `Ctrl+C`.

El asistente usa por dentro el mismo `sender/main.py`, así que valida lo
mismo y deja el mismo log. Para casos especiales, como retomar un envío que
se cortó, hay que usar los comandos de [Enviar mensajes](#enviar-mensajes).
