# Módulos y funcionamiento interno

Documentación de detalle de **osint-recon**. Para instalar y usar la herramienta,
mira el [README](../README.md).

## Cómo funciona

1. **Clasificación**: cada entrada se clasifica (`utils.detect_input_type`) como
   nombre, email, username, teléfono o dominio. La foto y la última ubicación vista
   llegan con su tipo explícito.
2. **Descubrimiento de módulos**: el orquestador carga solo todos los ficheros de
   `osintlib/modules/` (`modules.discover_modules`) y ejecuta sobre cada objetivo los
   módulos que lo aceptan (`BaseModule.accepts`).
3. **Grafo compartido**: cada módulo añade entidades y relaciones al grafo. Si dos
   módulos encuentran el mismo dato (mismo tipo y valor), se funde en un único nodo
   que acumula las fuentes. Esa es la base de la correlación.
4. **Correlación**: una fase final enlaza email ↔ username (misma parte local),
   persona ↔ objetivos de la misma investigación y teléfono ↔ brechas que
   expusieron teléfonos (`posible_filtracion`).
5. **Salida**: informe HTML, PDF y JSON, grafo (PNG, SVG, DOT, GraphML), mapa y
   línea de tiempo. La web y el informe usan el mismo modelo de vista
   (`osintlib/view.py`).

Si un módulo falla o le falta una herramienta o una clave, se marca como
`error`, `skipped` o `not_installed` en el informe y la ejecución continúa.

## Módulos

| Módulo | Fuente | Entrada | Red |
|---|---|---|---|
| `usernames` | Perfiles en 33 redes y servicios (GitHub, Reddit, Twitch, X, Instagram…) | nombre, email, username | sí |
| `breaches_free` | XposedOrNot: brechas de datos, gratis y sin clave | email | sí |
| `breaches` | Have I Been Pwned (requiere clave de pago) | email | sí |
| `permutations` | Genera emails candidatos a partir del nombre y los busca en brechas | nombre | sí |
| `domain` | WHOIS, DNS (A, AAAA, MX, NS, TXT, SOA) y cabeceras HTTP | dominio, email | sí |
| `external_tools` | **theHarvester** y **holehe** ejecutados por línea de comandos | dominio, email | sí |
| `phone` | phonenumbers: país, operadora, tipo de línea y zona horaria | teléfono | no |
| `interpol` | Notificaciones públicas de Interpol (Red y Yellow Notices) | nombre | sí |
| `news` | Noticias que mencionan el nombre (RSS de Google News) | nombre | sí |
| `exif` | Metadatos de una foto: GPS, fecha y dispositivo | imagen | no* |
| `reverse_image` | Enlaces de búsqueda inversa (Google Lens, Yandex, TinEye, Bing) | imagen | no |
| `missing_db` | Enlaces a bases de desaparecidos (SOS Desaparecidos, CNDES, NamUs, NCMEC, Amber Alert Europe) | nombre | no |
| `geocode` | Convierte la última ubicación vista en coordenadas (Nominatim) | lugar | sí |

\* `exif` solo usa la red si la foto es una URL.

### Usernames y variantes del nombre

A partir de un nombre se generan alias candidatos siguiendo la convención española
«Nombre Apellido1 Apellido2», que da prioridad al **primer apellido**. Para
«Mateo Rivas Olmedo»: `mateorivas`, `mateo.rivas`, `mrivas`, `mateo_rivas`,
`mateor`, `rivasmateo`, `mateoolmedo`, `mateo.olmedo`, `molmedo`, `mrivaso`.
No se prueban nombre ni apellido sueltos porque casi siempre pertenecen a otra
persona.

Un perfil se da por existente según el código HTTP y, en algunos sitios, el
contenido de la página. Algunos sitios bloquean clientes automáticos: esos casos
se cuentan como *comprobaciones ambiguas*, no como "no existe".

### Brechas de datos

- **`breaches_free`** (recomendado): API pública de [XposedOrNot](https://xposedornot.com/api_doc),
  sin clave. Límite: 2 peticiones/segundo, 25/hora y 100/día por IP.
- **`breaches`**: Have I Been Pwned, con clave de pago en `config.ini`
  (`[api_keys] hibp = ...`). Sin clave se omite.

En el informe las brechas aparecen **agrupadas por email**, así se ve a qué correo
pertenece cada una.

### Permutación de emails

Combina las variantes del nombre con los dominios de la investigación (`--domain` o
el dominio del email introducido) y busca cada candidato en XposedOrNot. Solo se
conservan los que aparecen en alguna brecha, marcados en el informe como
**candidato · verificar**. Los emails que ya forman parte de la investigación no se
vuelven a probar.

Ajustes en `config.ini`:

| Ajuste | Por defecto | Qué hace |
|---|---|---|
| `permute_emails` | `on` | Activa o desactiva el módulo |
| `permute_common` | `off` | Prueba también gmail, hotmail, outlook y yahoo. Da muchos falsos positivos |
| `permute_max` | `15` | Máximo de emails a comprobar (por el límite diario de la API) |

### Integración con herramientas externas

`external_tools` busca `theHarvester` y `holehe` en el PATH, los ejecuta como
procesos externos y parsea su salida:

- **theHarvester** (`-d dominio -b ... -f fichero`): lee el JSON que genera con
  emails, hosts e IPs.
- **holehe** (`email --only-used --no-color --no-clear`): lee las líneas `[+]` de
  los servicios donde el email tiene cuenta, incluidas las pistas de recuperación
  (email o teléfono parcialmente ocultos), e ignora la leyenda final.

Además, el grafo se dibuja ejecutando **Graphviz (`dot`)** y el PDF con
**Chromium/Chrome** en modo headless.

Si `pip install holehe` falla con `install_layout` o "externally-managed-environment",
instálalos aislados con pipx:

```bash
pipx install holehe
pipx install theHarvester
```

### Teléfono

Funciona sin conexión con la librería `phonenumbers`: validez, país, operadora,
tipo de línea y zona horaria. Describe el **número**, no identifica a su titular.
Para números sin prefijo se usa la región de `config.ini` (`phone_region = ES`).

No existe una búsqueda gratuita y fiable de brechas por teléfono. En su lugar, si
investigas a la vez un email y un teléfono y el email aparece en una brecha que
expuso teléfonos, se crea la relación tentativa `posible_filtracion`.

### Interpol y noticias

Son **coincidencias por nombre**, no confirmaciones: pueden ser homónimos. Por eso
llevan confianza baja y la etiqueta "verificar". Interpol admite filtros para
reducir homónimos: `--age`, `--nationality` y `--sex`. Solo se consultan las
notificaciones públicas.

Si Interpol devuelve `HTTP 403`, es su cortafuegos. El módulo ya envía cabeceras
de navegador; si persiste, suele ser un bloqueo por IP: prueba desde otra red.

### Personas desaparecidas

- **EXIF**: el GPS y la fecha de la foto van al mapa y a la línea de tiempo. Las
  redes sociales borran el EXIF al subir las fotos, así que funciona con el
  **archivo original**.
- **Búsqueda inversa**: prepara y enlaza las búsquedas en cada buscador (no extrae
  sus resultados automáticamente). No hace reconocimiento facial, porque eso trata
  datos biométricos (RGPD).
- **Última vez visto** (`--last-seen`, `--last-seen-date`): se geocodifica y aparece
  en el mapa, en la línea de tiempo y en las pistas prioritarias.

Esta parte **complementa, no sustituye** la denuncia: lo primero es 112, la
Guardia Civil o la Policía Nacional. Con menores, siempre por los canales
oficiales (NCMEC, 116000).

## Informe

- **Resumen** en lenguaje natural y **pistas prioritarias** (última vez visto, GPS
  de una foto, perfiles encontrados).
- Ubicaciones con enlaces a OpenStreetMap y Google Maps. El informe se abre como
  fichero local, y OpenStreetMap no sirve el mapa a ficheros locales; el mapa
  interactivo está en la web.
- Línea de tiempo con fechas legibles y tiempo relativo.
- Perfiles, EXIF, teléfono, brechas por email, Interpol, noticias, bases de
  desaparecidos y grafo.
- Botón de modo claro/noche. El detalle técnico (módulos y entidades) va plegado
  al final.

## Añadir un módulo

Crea un fichero en `osintlib/modules/`. No hay que registrarlo en ningún sitio:

```python
from ..entity import Entity, Graph
from .base import BaseModule, Context, ModuleResult


class MiFuenteModule(BaseModule):
    name = "mi_fuente"
    description = "Qué hace"
    accepts = ("email", "username")        # tipos de entrada que admite

    def run(self, target_type, target_value, graph, ctx) -> ModuleResult:
        res = ModuleResult(module=self.name, target=target_value)
        ent = graph.add_entity(Entity("email", target_value, sources=[self.name]))
        # ... consultar la fuente, crear entidades y relaciones ...
        res.message = "hecho"
        return res
```

## Limitaciones conocidas

- Los perfiles, las noticias y las coincidencias de Interpol pueden ser de
  homónimos: hay que verificarlos a mano.
- Algunos sitios limitan las peticiones o bloquean clientes automáticos.
- XposedOrNot tiene un límite diario de 100 consultas por IP.
- HIBP necesita una clave de pago.
