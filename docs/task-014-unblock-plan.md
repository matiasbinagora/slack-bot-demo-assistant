# Plan para desbloquear DAY-8-TASK-014

Fecha: 2026-08-22

## Decisiones aprobadas

1. La cancelación de un job de explicación no se implementa dentro de 4.4.
   Se documenta como excepción explícita y se crea un follow-up separado.
2. Se repara la salud estructural global de OpenSpec creando las rutas
   faltantes `openspec/specs/` y `openspec/changes/archive/`, con placeholders
   tracked y validación de `openspec doctor --json`.

## Estado de partida

- La hardening de cleanup está implementada en
  `feature/task-014-explain-cleanup`.
- Validación actual: 45 tests enfocados y 96 tests completos pasan.
- `openspec validate "mvp-slack-video-assistant" --json` pasa.
- `openspec doctor --json` falla porque faltan las dos rutas globales indicadas.
- El código tiene `cancel`, pero solo consume cancelación de una confirmación
  de exportación pendiente; no existe cancelación de un explanation job activo.
- No se ejecutó Slack/Anthropic live QA.

## Workstream A: salud de OpenSpec

1. Crear un task técnico separado para añadir placeholders mínimos en
   `openspec/specs/` y `openspec/changes/archive/`.
2. Ejecutar `openspec doctor --json` y `openspec validate` desde el worktree
   exacto de DAY-8-TASK-014.
3. Si el doctor reporta más problemas, detener el cierre y documentar el
   nuevo blocker; no rellenar specs globales sin una decisión adicional.

## Workstream B: excepción y follow-up de cancelación

1. Ajustar el contrato OpenSpec de 4.4 para hablar de estados terminales
   soportados y enlazar el follow-up de cancelación, sin inventar cobertura.
2. Crear una nueva propuesta OpenSpec para la cancelación de explanation jobs.
3. Crear la tarjeta `DAY-8-TASK-015` en Backlog, asignada a `backend-dev`, con
   requisitos de estado, coordinación con el executor, cleanup idempotente,
   carreras, respuesta segura y tests.
4. No iniciar implementación de cancelación hasta que la nueva propuesta,
   diseño, specs y tasks estén aprobados.

## Workstream C: cierre de 4.4

1. Refrescar Graphify y Codebase Memory del worktree exacto después de los
   cambios de documentación/estructura.
2. Repetir tests enfocados y completos, compileall, OpenSpec validate/doctor,
   diff check, revisión de secretos y smoke FFmpeg/FFprobe.
3. Actualizar la tarjeta `DAY-8-TASK-014` con la excepción y la evidencia.
4. Solo si todos los gates pasan, avanzar por Code Review y Functional Review
   y preparar un PR separado. No mover a Done ni mergear sin aprobación humana.

## Límites

- No se modifica el flujo de exportación ni se inicia ninguna tarea 5.x.
- No se añaden scopes, eventos Slack, credenciales, infraestructura ni
  persistencia.
- No se afirma cancelación de explicación ni Slack/Anthropic live QA.
- Los videos, transcripts, frames, URLs privadas y secretos permanecen fuera
  de prompts, logs, documentación y commits.

## Criterio de desbloqueo

DAY-8-TASK-014 puede salir de `Blocked` únicamente cuando:

1. La excepción de cancelación esté reflejada en OpenSpec y Trello, con
   `DAY-8-TASK-015` enlazada como follow-up.
2. `openspec doctor --json` y `openspec validate` pasen.
3. La suite de tests, compileall, diff check, revisión de secretos y smoke de
   FFmpeg/FFprobe tengan evidencia fresca.
4. Code Review y Functional Review no tengan blockers.
