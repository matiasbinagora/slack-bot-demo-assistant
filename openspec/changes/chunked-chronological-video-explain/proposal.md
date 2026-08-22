## Why

PR #8 controla el tamaño de la evidencia multimodal, pero la smoke test controlada todavía terminó en timeout de Claude. Una solicitud única para todo el video sigue concentrando evidencia, latencia y riesgo de fallo; el flujo `explain` necesita analizar intervalos temporales independientes y devolver una narración cronológica sin inventar los intervalos que no pudieron procesarse.

## What Changes

- Añadir una ruta de explicación segmentada que cubra el video completo en intervalos deterministas: 10 segundos para videos de hasta 30 segundos y 30 segundos para videos más largos, con un máximo de 10 segmentos dentro del límite MVP.
- Ejecutar una solicitud Claude independiente por segmento, con evidencia visual acotada y sin reutilizar una conversación o enviar Base64 de imágenes en el prompt textual.
- Renderizar una respuesta inglesa ordenada por intervalos absolutos, con `summary`, `key points` y timestamps solo cuando estén soportadas por la evidencia.
- Permitir fallos parciales de segmentos con una marca explícita de intervalo no disponible, pero detenerse ante fallos críticos de input/configuración o cuando no exista ningún resultado válido.
- Conservar el procesamiento asíncrono, el thread original, el presupuesto de request, la redacción de logs y el cleanup temporal del MVP.
- Añadir tests con mocks, fixtures FFmpeg/FFprobe y validación de límites, orden, presupuesto, fallos parciales y cleanup.

## Capabilities

### New Capabilities

- `chronological-explain`: segmentación temporal determinista, análisis independiente por intervalo y renderizado cronológico de resultados parciales seguros.

### Modified Capabilities

<!-- No main capability specs exist yet; the existing MVP change remains the baseline contract. -->

## Impact

- Afecta `media_pipeline.py`, `explanation_orchestrator.py`, `claude_analysis.py` y sus tests/fixtures.
- Añade artefactos OpenSpec para el nuevo contrato; no modifica la exportación ni marca task 4.4 como completada.
- No añade dependencias, scopes Slack, credenciales, infraestructura, persistencia ni cambios al límite del proveedor.
- La validación automatizada seguirá siendo mockeada y basada en fixtures propios. Una smoke test Slack/Claude controlada, si se ejecuta, será una evidencia separada de Functional Review y no se representará como cobertura de CI.

## Scope and Non-goals

### Scope

- Implementar la estrategia segmentada sobre el head de PR #8 en un follow-up separado.
- Mantener el contrato de entrada MP4 de hasta 100 MB y 300 segundos.
- Limitar cada segmento a hasta tres frames JPEG controlados y conservar la asociación temporal.

### Non-goals

- Reemplazar o hacer merge de PR #8.
- Exportación, crop, H.264/AAC, confirmación de exportación o resumen automático al subir.
- Activar Whisper, crear un motor de transcripción nuevo o duplicar un transcript global en cada segmento sin timestamps acotadas.
- Cambiar Socket Mode, scopes, credenciales, infraestructura, persistencia o límites del proveedor.

## Risks and Approval Gates

- Más llamadas pueden aumentar latencia, coste y probabilidad de timeout; el máximo será de 10 y no habrá reintentos automáticos duplicados.
- Los segmentos pueden producir resultados inconsistentes o evidencia sin audio; el renderer debe marcar degradación y no completar huecos con texto inventado.
- La salida agregada puede crecer; el formato debe ser estable y revisarse contra los límites de publicación de Slack.
- El cleanup debe abarcar tanto resultados parciales como fallos totales, sin registrar media, transcripts, rutas privadas o secretos.
- Se requiere Code Review antes de Functional Review, y aprobación humana antes de merge, cambiar credenciales/scopes o mover la tarjeta a `done`.
