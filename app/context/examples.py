"""Ejemplos few-shot de estimaciones históricas para inyectar en el prompt (CAG / RAG de contexto)."""

ESTIMATION_EXAMPLES = [
    {
        "meeting_summary": (
            "El cliente, una pyme de logística, necesita una plataforma web para gestionar "
            "almacenes, entradas/salidas de stock, alertas de mínimos y un panel para el "
            "responsable de compras. Integración futura con su ERP actual vía CSV (fase 2), "
            "pero en esta fase solo web responsive y roles internos (admin, operario, solo lectura)."
        ),
        "estimation": """
## Estimación: Plataforma web de gestión de inventario

### Desglose de tareas
1. Discovery, wireframes y diseño UI/UX responsive: 40 h · 3.200 €
2. Backend API REST (CRUD artículos, movimientos, ubicaciones): 60 h · 4.800 €
3. Autenticación, roles y auditoría básica de cambios: 22 h · 1.760 €
4. Dashboard con KPIs (rotación, valor stock, alertas): 32 h · 2.560 €
5. Importación/exportación CSV y jobs programados: 18 h · 1.440 €
6. Testing automatizado (API + E2E críticos) y QA manual: 28 h · 2.240 €
7. Despliegue, CI/CD y documentación técnica: 15 h · 1.200 €

**Total estimado: 215 h · ~17.200 €** (tarifa media orientativa 80 €/h)
**Equipo recomendado:** 2 desarrolladores full-stack + 1 diseñador UX a media jornada
**Duración estimada:** 7–9 semanas calendario (1 sprint de diseño + 3–4 de implementación)
**Riesgos / supuestos:** sin integración ERP en tiempo real en esta fase; datos maestros provistos por el cliente en semana 2.
""".strip(),
    },
    {
        "meeting_summary": (
            "Una fintech quiere un portal para clientes corporativos donde consulten extractos, "
            "descarguen facturas en PDF y abran incidencias de facturación. Debe cumplir accesibilidad "
            "AA, SSO con Azure AD del cliente y trazas de auditoría. El núcleo de pagos ya existe; "
            "este proyecto es solo capa B2B y reporting ligero."
        ),
        "estimation": """
## Estimación: Portal B2B de facturación e incidencias

### Desglose de tareas
1. Análisis de requisitos, flujos y diseño UI (WCAG AA): 36 h · 3.240 €
2. Front SPA (listados, filtros, detalle factura, descarga PDF): 52 h · 4.680 €
3. Integración SSO (OIDC / Azure AD) y gestión de sesiones: 24 h · 2.160 €
4. BFF/API gateway sobre servicios de facturación existentes: 44 h · 3.960 €
5. Módulo de tickets (creación, estados, comentarios, notificaciones email): 38 h · 3.420 €
6. Informes exportables (CSV/Excel) y límites de descarga: 20 h · 1.800 €
7. Seguridad (throttling, logs de auditoría), pentest remediación menor: 26 h · 2.340 €
8. QA regresión, accesibilidad y UAT con cliente: 30 h · 2.700 €

**Total estimado: 270 h · ~24.300 €** (tarifa media orientativa 90 €/h perfil senior)
**Equipo recomendado:** 1 tech lead / backend, 1 frontend, 0,5 QA; apoyo puntual DevOps
**Duración estimada:** 10–12 semanas (dependencia de entorno Azure AD y de APIs legacy)
**Riesgos / supuestos:** contratos de API de facturación estables; PDFs generados server-side ya disponibles o acordado alcance de generación nueva.
""".strip(),
    },
    {
        "meeting_summary": (
            "Una cooperativa agrícola quiere una app móvil (iOS y Android) para que los técnicos de campo "
            "registren visitas a fincas, fotos de plagas, geolocalización y sincronización offline cuando "
            "no hay cobertura. Panel web interno para coordinadores con mapa y listados. Sin pasarela de "
            "pago; autenticación con usuario/contraseña y MFA por TOTP."
        ),
        "estimation": """
## Estimación: App móvil de campo + panel web de coordinación

### Desglose de tareas
1. Discovery, flujos offline-first y diseño UI móvil/web: 44 h · 3.520 €
2. Backend API (visitas, adjuntos, colas de sincronización, resolución de conflictos): 72 h · 5.760 €
3. App móvil compartida (lista de tareas, formularios, cámara, almacenamiento local cifrado): 88 h · 7.040 €
4. Geolocalización, mapas y permisos (foreground/background según alcance acordado): 26 h · 2.080 €
5. Panel web (mapa, filtros, exportación CSV, gestión de usuarios): 48 h · 3.840 €
6. MFA TOTP, endurecimiento de sesiones y revisión de modelo de datos: 22 h · 1.760 €
7. Pruebas (unitarias API, pruebas de sincronización, E2E móvil críticos) y beta con 5 técnicos: 34 h · 2.720 €
8. Publicación en stores, pipelines CI/CD y manual de usuario: 24 h · 1.920 €

**Total estimado: 358 h · ~28.640 €** (tarifa media orientativa 80 €/h)
**Equipo recomendado:** 1 desarrollador mobile, 1 backend, 0,5 diseñador UX; apoyo puntual QA
**Duración estimada:** 12–14 semanas calendario (stores y pruebas offline suelen alargar 1–2 semanas)
**Riesgos / supuestos:** políticas de retención de fotos y RGPD definidas por el cliente; límites de tamaño de adjuntos acordados antes del sprint 2.
""".strip(),
    },
    {
        "meeting_summary": (
            "Una cadena de tiendas físicas quiere un catálogo online con carrito, stock en tiempo casi "
            "real desde su POS actual (webhooks diarios como mínimo), envíos solo península y pasarela "
            "de pago estándar. CMS sencillo para marketing (banners, colecciones). SEO básico y "
            "Google Analytics 4."
        ),
        "estimation": """
## Estimación: E-commerce catálogo + stock POS + CMS marketing

### Desglose de tareas
1. Arquitectura, modelo de catálogo, SEO técnico base y diseño UI tienda: 52 h · 4.680 €
2. Front tienda (PLP/PDP, carrito, checkout, emails transaccionales): 78 h · 7.020 €
3. Integración pasarela de pago y gestión de estados de pedido: 32 h · 2.880 €
4. Conector stock POS (webhooks + job de conciliación y alertas de discrepancia): 46 h · 4.140 €
5. CMS headless o panel admin para banners/colecciones y preview: 38 h · 3.420 €
6. Logística península (tasas, etiquetas con transportista acordado vía API): 28 h · 2.520 €
7. GA4, consentimiento cookies y hardening básico (headers, rate limit): 20 h · 1.800 €
8. QA E2E, carga ligera y formación a equipo de tienda: 26 h · 2.340 €

**Total estimado: 320 h · ~28.800 €** (tarifa media orientativa 90 €/h)
**Equipo recomendado:** 1 full-stack lead, 1 frontend, 0,5 backend integraciones; copy legal externo si aplica
**Duración estimada:** 9–11 semanas (depende de documentación del POS y del transportista)
**Riesgos / supuestos:** API del POS documentada o acceso a sandbox en semana 1; política de devoluciones acordada antes del checkout.
""".strip(),
    },
    {
        "meeting_summary": (
            "El departamento de operaciones de un hospital público (sin datos clínicos en esta fase) "
            "pide un cuadro de mando interno: ocupación de camas agregada, tiempos de limpieza, "
            "incidencias de mantenimiento y SLA. Fuentes: varias hojas Excel en carpetas de red y un "
            "CSV diario de un sistema legado. Solo intranet; login con LDAP del centro."
        ),
        "estimation": """
## Estimación: Cuadro de mando operativo (intranet + ETL ligero)

### Desglose de tareas
1. Taller con operaciones, definición de KPIs y diccionario de datos: 28 h · 2.240 €
2. Ingesta programada (lectura Excel/CSV, validaciones, capa staging en BD): 42 h · 3.360 €
3. Modelo dimensional simple y jobs idempotentes con logs y alertas de fallo: 36 h · 2.880 €
4. Autenticación LDAP, roles (solo lectura vs editor de umbrales) y auditoría de accesos: 24 h · 1.920 €
5. Front dashboards (filtros fecha/servicio, gráficos, tablas drill-down exportables): 56 h · 4.480 €
6. Gestión de umbrales SLA e histórico de incidencias (CRUD acotado): 30 h · 2.400 €
7. Observabilidad (métricas jobs), backups configurados y runbook: 18 h · 1.440 €
8. UAT con usuarios clave, formación corta y ajustes de rendimiento: 22 h · 1.760 €

**Total estimado: 256 h · ~20.480 €** (tarifa media orientativa 80 €/h)
**Equipo recomendado:** 1 ingeniero de datos/backend, 1 frontend/analítica; sin acceso a datos clínicos identificables
**Duración estimada:** 8–10 semanas (la calidad y ubicación de los Excels condiciona la fase de ingesta)
**Riesgos / supuestos:** rutas de red y permisos de lectura estables; se excluye integración HL7/FHIR y cualquier dato de paciente.
""".strip(),
    },
]
