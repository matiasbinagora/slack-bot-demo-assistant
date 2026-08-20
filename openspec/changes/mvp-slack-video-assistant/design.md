## Context

El repositorio solo contiene el bootstrap de agentes, documentación y contrato MVP. La primera implementación debe crear un proceso Python local que se conecte a Slack mediante Socket Mode, reciba archivos y mensajes en threads, ejecute procesamiento multimedia y use Claude Agent SDK sin almacenar medios de forma permanente.

Las restricciones principales son: MP4 de hasta 100 MB y 5 minutos, respuestas del usuario en inglés, salida MP4 H.264/AAC, crop centrado, limpieza de artefactos temporales y ausencia de workspace Slack real para QA.

## Goals / Non-Goals

**Goals:**

- Proveer un entrypoint local para un bot Slack Bolt conectado por Socket Mode.
- Mantener una frontera clara entre handlers Slack, estado de thread, procesamiento multimedia y Claude.
- Reconocer una subida MP4, responder en el thread y procesar únicamente solicitudes explícitas de explicación o exportación.
- Validar límites antes de usar Claude o FFmpeg y limpiar artefactos en todas las rutas.
- Permitir tests deterministas con mocks de Slack/Claude y fixtures MP4.

**Non-Goals:**

- OAuth multi-workspace, despliegue productivo, alta disponibilidad o cola distribuida.
- Resumen automático al subir el archivo.
- Persistencia de sesiones, videos, transcripciones o outputs fuera del ciclo de una solicitud.
- Subject tracking, crop inteligente o formatos arbitrarios.
- Pruebas contra servicios reales en CI o afirmaciones de funcionamiento real en Slack sin evidencia separada.

## Decisions

### 1. Socket Mode con Slack Bolt y configuración por entorno

El proceso usará Slack Bolt con Socket Mode. `SLACK_BOT_TOKEN` y `SLACK_APP_TOKEN` se leerán exclusivamente del entorno; la aplicación fallará de forma explícita si falta una credencial obligatoria. La configuración documentará los eventos y scopes mínimos para leer archivos y publicar respuestas, incluyendo `files:read` y `chat:write` cuando el workspace los requiera.

**Alternativas consideradas:** HTTP Events API habría requerido una URL pública y despliegue adicional; se descarta para el MVP local-first. Un polling de Slack no ofrece una interacción adecuada ni reduce la complejidad de permisos.

### 2. Handlers rápidos y procesamiento asíncrono local

Los handlers harán acknowledge inmediato y publicarán un estado breve en el thread. El procesamiento pesado se ejecutará fuera del callback mediante una unidad asíncrona o worker local acotado. El estado de una sesión se identificará por workspace, channel y thread timestamp, y vivirá solo durante el ciclo de la solicitud.

El flujo inicial será explícito y testeable: una subida MP4 recibe acuse, `explain` o una solicitud equivalente dispara la explicación, `export` inicia la sugerencia y `confirm`/`cancel` resuelven la confirmación. No se generará un resumen automático al subir el archivo.

**Alternativas consideradas:** procesar dentro del callback sería simple pero puede bloquear el Socket Mode y provocar reintentos; una cola externa añade infraestructura y persistencia que no son necesarias para desarrollo local.

### 3. Cliente Slack aislado del dominio

Un adaptador encapsulará descarga autenticada de archivos, publicación de mensajes y publicación del MP4 resultante. Las URLs de Slack se tratarán como referencias no confiables: no se pasarán directamente a Claude, no se imprimirán en logs y se descargará el contenido a una ruta temporal controlada.

### 4. Frontera explícita para Claude Agent SDK

El dominio recibirá una interfaz de análisis que acepte evidencia multimedia local y una solicitud de usuario, y devuelva un resultado estructurado o un error tipado. La implementación concreta usará Claude Agent SDK y `ANTHROPIC_API_KEY` desde el entorno. Los prompts no contendrán tokens, URLs privadas ni instrucciones que conviertan contenido de video o transcripciones en configuración del sistema.

En tests se mockeará la interfaz; no se harán llamadas reales a Claude. Los errores de proveedor, timeout o respuesta inválida se mostrarán como fallos y nunca como una explicación exitosa.

### 5. Pipeline temporal de medios

Cada solicitud tendrá un directorio temporal privado. La descarga aplicará límite de bytes durante el streaming; FFprobe validará contenedor, codec/duración y dimensiones antes de continuar. FFmpeg generará frames, audio y el output de exportación dentro de ese directorio. Un bloque de cleanup se ejecutará después de éxito, error o cancelación.

**Alternativas consideradas:** almacenamiento permanente simplificaría reintentos, pero contradice la política de retención mínima; una base de datos de sesiones añadiría un sistema que el MVP no necesita.

### 6. Exportación confirmada con ratios limitados

El bot sugerirá un ratio estándar entre `16:9`, `9:16` y `1:1`, mostrará la intención de crop centrado y esperará confirmación positiva. FFmpeg se ejecutará solo después de la confirmación. FFprobe verificará H.264/AAC, contenedor MP4, dimensiones y existencia de audio antes de publicar el archivo.

### 7. Evidencia de validación

La validación será por capas: tests unitarios de dominio, tests de handlers con payloads Slack simulados, fixtures MP4 para FFmpeg/FFprobe, revisión de cleanup y checks de configuración. No se considerará validación real de Slack ni de Claude salvo que un entorno autorizado aporte evidencia independiente; esa evidencia no es requisito del MVP local.

### 8. Regla continua de sincronización del contrato

Si la implementación aprobada cambia comportamiento observable, dependencias operativas del flujo, comandos soportados, límites, codecs, cleanup, validaciones o expectativas de QA, `backend-dev` deberá actualizar en la misma PR el artefacto relevante de OpenSpec (`design.md`, la spec afectada y/o `tasks.md`) antes de solicitar revisión. Ninguna divergencia entre implementación y contrato puede quedar solo en comentarios de código o en la descripción de la PR.

## Risks / Trade-offs

- **[Permisos Slack incorrectos]** → Documentar scopes/eventos y cubrir respuestas con payloads simulados; requerir aprobación humana antes de cambiar permisos.
- **[Bloqueo del Socket Mode]** → Acknowledge inmediato y worker local acotado; probar que el callback no ejecuta FFmpeg ni Claude directamente.
- **[Contenido no confiable]** → Validar archivos con streaming y FFprobe, usar rutas temporales controladas y separar contenido de instrucciones del sistema.
- **[Fuga de secretos o URLs]** → Leer credenciales solo del entorno, redactar logs y añadir revisión de seguridad.
- **[Diferencia entre mocks y servicios reales]** → Marcar explícitamente la cobertura simulada y no afirmar QA live Slack.
- **[Cleanup prematuro o incompleto]** → Publicar/validar el resultado antes de borrar y probar cleanup en éxito, error y cancelación.
- **[Estado de confirmación ambiguo]** → Usar estados explícitos por thread, comandos canónicos (`export`, `confirm`, `cancel`) y pruebas de repetición/out-of-order.
- **[Contrato OpenSpec desactualizado]** → Exigir actualización del artefacto relevante en la misma PR cuando cambie el comportamiento implementado.

## Migration Plan

1. Documentar la configuración Slack y Claude sin valores secretos.
2. Añadir el entrypoint y el adaptador Slack con handlers sin procesamiento pesado.
3. Añadir el cliente Claude mockeable y el pipeline de comprensión con fixtures.
4. Añadir el pipeline de exportación y validación FFprobe.
5. Ejecutar tests, checks de seguridad y validación multimedia local.
6. Para rollback, detener el proceso local y retirar las credenciales del entorno; no hay migración de datos porque el diseño no persiste medios ni sesiones.

## Open Questions

- Confirmar los scopes exactos para el tipo de canal Slack usado durante la primera prueba autorizada.
- Confirmar si Whisper local se habilitará en la primera implementación o si la explicación empezará solo con frames.
- Confirmar si el mensaje de respuesta debe adjuntar siempre el output de exportación o puede entregar una referencia temporal; la política local exige borrar el archivo después del ciclo.
