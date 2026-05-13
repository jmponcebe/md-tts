# Sample document for md-tts

> Una nota inicial en formato blockquote. Debe leerse precedida de "Cita:".

Este es un párrafo en **español** con `código inline` y un enlace a [GitHub](https://github.com). El parser debería detectar idioma español automáticamente y elegir una voz acorde.

This second paragraph is written in English. The parser still detects the language per paragraph, but the current reader chooses a single session voice based on the dominant language of the whole document, so you should hear this one in whichever voice md-tts picked at startup.

---

## Sección 1 — Listas y formato

Aquí va una lista no ordenada con elementos cortos:

- Primer ítem de la lista
- Segundo ítem, un poco más largo para ver cómo se lee
- Tercer ítem con `código inline` dentro

Y ahora una lista ordenada:

1. Paso uno: descargar dependencias
2. Paso dos: ejecutar tests
3. Paso tres: hacer commit y push

## Section 2 — Code blocks

A short Python snippet to trigger an interactive pause:

```python
def greet(name: str) -> str:
    return f"hello {name}"
```

Some prose between code blocks. A bash example:

```bash
uv sync --extra dev
uv run pytest -v
```

And a longer block to verify the preview is fully shown in the terminal:

```python
from dataclasses import dataclass


@dataclass
class Block:
    kind: str
    content: str
    raw_preview: str
    info: str = ""
    extra: str = ""
```

## Sección 3 — Tablas

Tabla con cabecera y dos columnas:

| Columna A | Columna B |
| --------- | --------- |
| valor 1   | valor 2   |
| valor 3   | valor 4   |
| valor 5   | valor 6   |

Tabla con tres columnas y filas más largas:

| Componente | Tecnología       | Notas                          |
| ---------- | ---------------- | ------------------------------ |
| API        | FastAPI 0.115    | Sirve /query y /agent/query    |
| UI         | Streamlit 1.54   | Modo chat con sources tab      |
| Graph      | Neo4j 5 Aura     | 12K nodos, 380K relaciones     |

## Section 4 — Headings deep dive

### Subsection with question?

Un párrafo bajo una subsección cuyo título termina en interrogación. No debe sonar como "interrogación punto".

### Otra subsección sin puntuación final

Texto bajo subsección sin signo final, debería añadirse un punto al hablar.

## Sección 5 — Flashcards

Tres flashcards seguidas para probar el modo Q→pausa→A:

<details>
<summary>¿Qué hace md-tts?</summary>
Lee Markdown técnico en voz alta con pausas interactivas en bloques de código, tablas y flashcards.
</details>

<details>
<summary>What is the default speech rate?</summary>
185 words per minute, configurable via --rate.
</details>

<details>
<summary>¿Cómo se activa el modo podcast?</summary>
Con la opción --no-pause; el lector anuncia los bloques saltados en lugar de esperar ENTER.
</details>

## Sección 6 — Contenido mixto y bordes

Una imagen inline en medio de un párrafo: aquí ![diagrama de arquitectura](docs/arch.png) y sigue el texto.

Un párrafo con varios formatos: **negrita**, *cursiva*, ~~tachado~~, `código`, y una fórmula simulada como texto: E = mc². La frase contiene una pregunta clave, ¿se pronuncia bien?

Un bloque de cita largo:

> Cuando un sistema MLOps falla en producción, la causa raíz suele estar en la diferencia entre los datos de entrenamiento y los de inferencia. Por eso es esencial monitorizar la deriva de datos con herramientas como Evidently o Whylogs.

Otro separador:

---

## Section 7 — Edge cases for the parser

Single-line paragraph.

Two-line
paragraph with a soft break that should be read as a single sentence.

Párrafo con números: en 2026 había 263 tests en PharmaGraphRAG y 88 en DengueMLOps. La diferencia entre 3.0.5 y 3.1.0 es un patch release.

Lista anidada para verificar comportamiento:

- Nivel 1 ítem A
  - Nivel 2 sub-ítem A1
  - Nivel 2 sub-ítem A2
- Nivel 1 ítem B

Una flashcard con respuesta de varias líneas:

<details>
<summary>¿Qué es ReAct en el contexto de agentes LLM?</summary>
ReAct (Reasoning + Acting) es un patrón donde el agente alterna entre razonamiento (think) y acción (tool call). LangGraph implementa este patrón nativamente con create_react_agent. Permite al LLM decidir qué herramienta usar y observar el resultado antes de razonar el siguiente paso.
</details>

## Fin

Este es el último párrafo del documento. Si lo escuchas hasta aquí, md-tts ha procesado todos los bloques correctamente.
