## Why

El repositorio tiene el contrato de producto y la gobernanza inicial, pero todavía no tiene un flujo ejecutable para recibir mensajes y archivos desde Slack, procesar videos ni consultar Claude. Este cambio define la primera rebanada implementable del MVP local-first para que un usuario pueda interactuar con el bot, obtener una explicación bajo demanda y generar una exportación confirmada.

## What Changes

- Configurar una aplicación Slack con Socket Mode, sus credenciales por entorno, el proceso Python y los handlers necesarios para responder en threads.
- Definir una frontera testeable para Claude Agent SDK, incluyendo configuración, errores de proveedor y ausencia de secretos en el repositorio.
- Validar y descargar de forma segura videos MP4 desde Slack, respetando los límites de 100 MB y 5 minutos.
- Procesar una solicitud explícita de explicación y devolver resumen, puntos clave y timestamps en inglés.
- Añadir un flujo de exportación que sugiera formato y relación de aspecto, espere confirmación y produzca MP4 H.264/AAC con crop centrado.
- Eliminar videos, frames, transcripciones y salidas locales al finalizar cada solicitud, incluso cuando falla.
- Añadir tests con mocks y fixtures de video propios; no se incluye validación contra un workspace Slack real.

## Scope

- Desarrollo local de un único workspace Slack mediante Socket Mode.
- Interacción iniciada por el usuario dentro de un thread.
- MP4 como único formato de entrada y salida del MVP.
- Backend Python con Slack Bolt, Claude Agent SDK, FFmpeg/FFprobe y Whisper únicamente si se decide habilitar audio local.

## Non-goals

- Almacenamiento permanente de medios o transcripciones.
- OAuth multi-workspace, despliegue productivo o alta disponibilidad.
- Resumen automático inmediatamente después de la subida.
- Formatos arbitrarios, subject tracking o crop inteligente.
- Verificación funcional en un workspace Slack real durante esta fase.

## Capabilities

### New Capabilities

- `slack-interaction`: configuración de la aplicación Slack, Socket Mode, proceso Python, recepción de eventos, respuestas en threads y acceso autenticado a archivos.
- `claude-integration`: configuración por entorno y frontera testeable para Claude Agent SDK, con manejo explícito de errores y datos no confiables.
- `video-understanding`: validación de MP4, extracción de evidencia, explicación bajo demanda en inglés, límites y cleanup.
- `video-export`: confirmación de formato/aspect ratio, crop centrado, exportación H.264/AAC y validación FFprobe.

### Modified Capabilities

- Ninguna. No existen specs base en `openspec/specs/`.

## Impact

- Nuevos módulos Python para el proceso Slack, handlers, configuración, clientes de Claude y pipeline multimedia.
- Nuevos tests, fixtures MP4 y comandos de validación local.
- Dependencias runtime planificadas: Slack Bolt, Claude Agent SDK y herramientas FFmpeg/FFprobe; cualquier instalación requiere aprobación separada.
- Variables de entorno y permisos/scopes Slack documentados sin guardar valores secretos.

## Risks

- Scopes o credenciales Slack insuficientes para descargar archivos o publicar respuestas.
- Exposición accidental de tokens, URLs privadas, videos o transcripciones en logs.
- Archivos multimedia malformados que consuman recursos o evadan validaciones.
- Diferencias entre mocks y servicios reales de Slack/Claude.
- Pérdida de evidencia local si el cleanup se ejecuta antes de completar la respuesta.

## Approval Gates

- Aprobación humana antes de cambiar credenciales, scopes Slack, dependencias o infraestructura.
- Code Review antes de Functional Review.
- Functional Review con mocks y fixtures antes de cualquier afirmación de funcionamiento real en Slack.
- Aprobación humana antes de mover cards a `done` o cerrar trabajo.
