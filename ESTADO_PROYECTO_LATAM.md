# ESTADO DEL PROYECTO — LegalTech LATAM
**Ultima actualizacion:** 2026-04-26 (sesion tarde)

---

## 1. RESUMEN EJECUTIVO
Plataforma RAG legal/fiscal para Uruguay (Fase 1) y Mercosur.
Motor de extraccion de normativa oficial con scraping automatizado,
almacenamiento en Dropbox, e indexacion futura para consultas en
lenguaje natural con cita obligatoria de fuente original.

Valor diferencial vs competencia: toda respuesta incluye URL a fuente oficial.

---

## 2. INFRAESTRUCTURA

| Componente | Detalle | Estado |
|---|---|---|
| Repo GitHub | github.com/paragitpc/web-scraper (publico) | OK activo |
| Dropbox | Apps/normativa-sync/ 700GB disponibles | OK activo |
| Secret DROPBOX_REFRESH_TOKEN | cargado en GitHub | OK |
| Secret DROPBOX_APP_KEY | cargado en GitHub | OK |
| Secret DROPBOX_APP_SECRET | cargado en GitHub | OK |
| Python venv | 3.12 en contable-uy-backfill/.venv | OK |

Carpeta local activa: /home/pablo/Documents/Proyecto_SCRAP/contable-uy-backfill/

---

## 3. COMMITS IMPORTANTES

| Hash | Descripcion |
|---|---|
| 190eff7 | fix: workflow args vacios impo_decretos/resoluciones_mef |
| 4cbfa17 | feat: API JSON de IMPO (impo_leyes + impo_decretos reescritos) |
| af692df | update dropbox auth |
| 637c172 | add scrapers and pipeline |

---

## 4. SCRAPERS

### FUNCIONANDO Y EN PRODUCCION
| Scraper | Metodo | Notas |
|---|---|---|
| impo_diario.py | PDF directo httpx | Diario Oficial PDF por fecha |
| impo_leyes.py | API JSON IMPO | encoding latin-1 |
| impo_decretos.py | API JSON IMPO | requiere from-year/to-year + from-n/to-n |
| dgi_normativa.py | httpx directo | TO2023 PDF (100MB) + 7 paginas HTML estaticas DGI |

### BLOQUEADOS - requieren sesion IMPO
| Scraper | Problema | Solucion planificada |
|---|---|---|
| impo_resoluciones_mef.py | Servidor nuevo pide sesion | Playwright + cookie idsesionanonimo |
| dgi_consultas_vinculantes.py | Idem | Idem |
| dgi_consultas_no_vinculantes.py | Idem | Idem |
| dgi_resoluciones.py | Idem | Idem |

### SIN PROBAR - Parte 2
BPS, MTSS, BCU, AIN, CCEAU, DNA, TCA, SCJ, Parlamento, INE

---

## 5. API JSON DE IMPO

URL: https://www.impo.com.uy/bases/<tipo>/<numero>-<anio>?json=true
Encoding: latin-1
Licencia: Datos Abiertos Uruguay
Funciona: leyes, decretos, constitucion, codigos, textos ordenados
NO funciona: resoluciones MEF, consultas DGI (requieren sesion)

---

## 6. ARQUITECTURA DROPBOX

Apps/normativa-sync/
  uy/
    impo_diariooficial/AAAA/MM/AAAA-MM-DD.pdf
    impo_leyes/NNNNN/data.json
    impo_decretos/AAAA/NNNNN-AAAA/data.json
    _index/
      impo_diariooficial.jsonl
      impo_leyes.jsonl
      impo_decretos.jsonl

Cuando se agregue Argentina: Apps/normativa-sync/ar/...

---

## 7. BACKFILLS - ESTADO

| Job | Source | Rango | Extra | Estado |
|---|---|---|---|---|
| 1 | impo_leyes | 18000-20500 | - | CORRIENDO 2026-04-26 |
| 2 | impo_leyes | 1-17999 | - | CORRIENDO 2026-04-26 |
| 3 | impo_decretos | 2020-2026 | 1-600 | CORRIENDO 2026-04-26 |
| 4 | impo_decretos | 2000-2019 | 1-600 | CORRIENDO 2026-04-26 |
| 5 | impo_diario | 2019-02-01/2019-12-31 | - | CORRIENDO 2026-04-26 |
| 6 | impo_diario | 2005-01-01/2009-12-31 | - | PENDIENTE |
| 7 | impo_decretos | 1990-1999 | 1-600 | PENDIENTE |
| 8 | impo_leyes | post-20500 | - | PENDIENTE futuro |

---

## 8. PROXIMOS PASOS EN ORDEN

1. OK Jobs 6A y 6B lanzados: impo_diario 2005-2014
2. OK dgi_normativa.py creado, probado y en GitHub
3. PENDIENTE Agregar dgi_normativa al workflow run-scraper.yml
4. PENDIENTE Crear cron diario (daily.yml) para todos los scrapers
5. PENDIENTE Scrapers bloqueados: Playwright + cookie idsesionanonimo
6. PENDIENTE Scrapers Parte 2: BPS, MTSS, BCU, AIN, etc.
7. PENDIENTE Pipeline OCR para PDFs escaneados
8. PENDIENTE Capa RAG: pgvector + embeddings

---

## 9. FUENTES TAXONOMIA COMPLETA - Uruguay

### Transversales
| Fuente | URL | Estado |
|---|---|---|
| IMPO Diario Oficial | impo.com.uy/diariooficial | OK activo |
| IMPO Leyes/Decretos | impo.com.uy/bases | OK activo |
| DGI/MEF | gub.uy/dgi | BLOQUEADO pendiente sesion |
| BPS | bps.gub.uy | SIN PROBAR |
| MTSS | mtss.gub.uy | SIN PROBAR |
| SENACLAFT | senaclaft.gub.uy | SIN PROBAR |
| URCDP | urcdp.gub.uy | SIN PROBAR |
| AIN/CJPPU | ain.gub.uy | SIN PROBAR |

### Verticales
| Fuente | URL | Estado |
|---|---|---|
| BCU/Fintech | bcu.gub.uy | SIN PROBAR |
| MGAP/Trazabilidad | mgap.gub.uy | SIN PROBAR |
| VUCE/Aduanas | vuce.gub.uy | SIN PROBAR |
| ANV/Intendencias | anv.gub.uy | SIN PROBAR |
| Zonas Francas | mef.gub.uy | SIN PROBAR |

### Nicho Especializado
| Fuente | URL | Estado |
|---|---|---|
| URSEA | ursea.gub.uy | SIN PROBAR |
| MSP/Farmaceutica | msp.gub.uy | SIN PROBAR |
| DIGEFE | minterior.gub.uy | SIN PROBAR |
| ARCE/TOCAF | arce.gub.uy | SIN PROBAR |
| MAOT | ambiente.gub.uy | SIN PROBAR |

---

## 10. ESTRATEGIA CRON DIARIO

El cron diario (daily.yml) debe correr automaticamente cada dia y cubrir:

| Scraper | Modo diario | Logica |
|---|---|---|
| impo_diario.py | fecha de ayer | 1 PDF por dia |
| impo_leyes.py | ultimas 50 leyes | from-id = ultimo conocido |
| impo_decretos.py | anio actual, ultimos 50 | rolling window |
| dgi_normativa.py | mode=all | re-descarga si cambia hash |

Regla anti-gap: el primer run del cron debe arrancar desde 2026-04-25
para no dejar hueco entre los backfills y el daily.

Workflow daily.yml: activado con schedule cron '0 6 * * *' (6am UTC = 3am Uruguay)

---

## 11. NOTAS TECNICAS CLAVE

- Anio dummy en leyes: IMPO ignora el anio en leyes-originales, usar N-2025
- Cookie sesion IMPO: idsesionanonimo generada automaticamente al navegar
- Node.js 20 deprecation: forzado el 2 junio 2026, actualizar antes
- Dropbox App Folder (no Full): seguridad, la app solo toca su carpeta
- Cursor para codear, Claude para guiar e investigar sitios
- Dropbox espacio: 700GB disponibles de 2TB

---

## 11. INSTRUCCIONES PARA RETOMAR EN NUEVA SESION

1. Subir este archivo a Claude al inicio de cada sesion
2. Decirle: retoma el proyecto desde ESTADO_PROYECTO_LATAM.md
3. El asistente debe preguntar: que jobs corrieron y cuales terminaron
4. Luego continuar por PROXIMOS PASOS secuencialmente
