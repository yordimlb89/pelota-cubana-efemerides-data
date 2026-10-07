# Efemérides de Pelota Cubana Stats

Preparación independiente de la Serie Nacional. Scripts Python sin IA ni agentes.

## Estado de la migración

Repositorio público autorizado por el propietario. Actualización diaria a las 06:00 de America/New_York y ejecución manual. La tarea anterior de Sites se apaga después de verificar la conexión publicada. No se ha cambiado la Serie Nacional.

## Qué conserva

Base publicada v425, commit 09dba073245d0408e9ec958e7282befb10c9da46, con 1.894 personas y 1.806 hechos. Incluye las 549 efemérides editoriales y todas las biografías, fuentes y registros históricos anteriores. `pending.json` conserva el archivo de hechos pendientes del sitio. No contiene PDFs, credenciales ni código privado del sitio.

## Actualización

`python update.py --days 7` consulta partidos finalizados oficiales de MLB y ligas menores afiliadas, y las biografías de jugadores ya identificados mediante ID. Lee los boxscores publicados por el repositorio de Serie 65, sin escribir allí ni consultar de nuevo el servidor cubano. Detecta 3+ HR (2+ en postemporada), 5+ hits, 7+ CI, ciclo, 15+ ponches y juegos completos de nueve entradas sin hits confirmados explícitamente en MLB. No declara récords históricos.

La salida `data.json` tiene el mismo esquema del calendario. Una caída de fuente o error de validación evita publicar esa ejecución. Cada cambio queda versionado. Una corrección oficial solo puede retirar detecciones automáticas del partido comprobado; nunca elimina el archivo editorial. Fechas ausentes de fallecimiento no borran fechas anteriores. Posibles duplicados van a `automatic-pending.json`.

No busca ni interpreta automáticamente artículos. Noticias, títulos, premios, nuevas identidades y otras ligas sin un adaptador comprobado necesitan revisión humana y una fecha exacta. No se utiliza la fecha de publicación de una noticia como fecha del hecho. Las aportaciones de conversaciones privadas no son accesibles a estos scripts.

## Separación de la Serie Nacional

Repositorio, workflow, caché y concurrencia propios. El token automático de Actions solo escribe en este repositorio. No necesita tokens personales ni secretos del sitio. No modifica horarios, archivos, datos, workflows ni permisos de `pelota-cubana-serie65-data`. Leer su JSON no ejecuta su workflow.

## Validación y activación

`python -m unittest -v test_update.py` y `python update.py --validate-only`.
La ejecución manual prueba las fuentes reales. Al conectar el sitio, combinar por claves estables con su archivo local y conservar este último como respaldo. Las altas editoriales del sitio tienen prioridad sobre las copias anteriores del repositorio. La tarea de IA se desactiva solo después de publicar y verificar esa conexión.

Horario configurado: 06:00 de America/New_York. GitHub puede retrasar la ejecución según su disponibilidad.
